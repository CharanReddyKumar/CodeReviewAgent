from __future__ import annotations

import logging
import schedule
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from agents.semgrep_agent import SemgrepAgent
from knowledge_graph.graph_store import GraphStore
from graph_defination import normalize_repo_reference, repo_slug

logger = logging.getLogger(__name__)


class SecurityScanner:
    """
    Proactive security scanner that runs daily repo-wide scans.
    Integrates with SAST tools and stores results in the knowledge graph.
    """

    def __init__(
        self,
        repo_path: Path,
        graph_store: Optional[GraphStore] = None,
        repo_reference: Optional[str] = None,
    ):
        self.repo_path = Path(repo_path)
        self.graph_store = graph_store
        self.semgrep_agent = SemgrepAgent(repo_path)
        self.scan_history: List[Dict[str, Any]] = []
        self.is_running = False
        self.repo_reference = (
            normalize_repo_reference(repo_reference)
            if repo_reference
            else None
        )
        self.repo_slug = repo_slug(self.repo_reference) if self.repo_reference else None
        self._repo_root = self.repo_path.resolve()

    def run_full_scan(self) -> Dict[str, Any]:
        """
        Run a comprehensive security scan of the entire repository.
        
        Returns:
            Scan results with vulnerabilities found
        """
        logger.info(f"Starting full security scan of {self.repo_path}")
        scan_start = datetime.now(timezone.utc)
        
        # Run Semgrep scan
        vulnerabilities = []
        try:
            findings = self.semgrep_agent.scan_repository()
            vulnerabilities.extend(findings)
        except Exception as exc:
            logger.error(f"Semgrep scan failed: {exc}")
        
        # TODO: Add more SAST tools (Bandit for Python, etc.)
        
        scan_result = {
            'scan_id': f"scan_{scan_start.strftime('%Y%m%d_%H%M%S')}",
            'timestamp': scan_start.isoformat(),
            'repo_path': str(self.repo_path),
            'repo_reference': self.repo_reference,
            'repo_slug': self.repo_slug,
            'total_vulnerabilities': len(vulnerabilities),
            'vulnerabilities': vulnerabilities,
            'severity_breakdown': self._count_by_severity(vulnerabilities),
            'category_breakdown': self._count_by_category(vulnerabilities)
        }
        
        # Store in graph if available
        if self.graph_store:
            self._store_scan_results(scan_result)
        
        # Add to history
        self.scan_history.append(scan_result)
        
        logger.info(
            f"Security scan complete: {len(vulnerabilities)} vulnerabilities found "
            f"(Critical: {scan_result['severity_breakdown'].get('critical', 0)}, "
            f"High: {scan_result['severity_breakdown'].get('high', 0)})"
        )
        
        return scan_result

    def _count_by_severity(self, vulnerabilities: List[Dict]) -> Dict[str, int]:
        """Count vulnerabilities by severity level."""
        counts = {}
        for vuln in vulnerabilities:
            severity = vuln.get('severity', 'unknown').lower()
            counts[severity] = counts.get(severity, 0) + 1
        return counts

    def _count_by_category(self, vulnerabilities: List[Dict]) -> Dict[str, int]:
        """Count vulnerabilities by category."""
        counts = {}
        for vuln in vulnerabilities:
            category = vuln.get('category', 'unknown')
            counts[category] = counts.get(category, 0) + 1
        return counts

    def _store_scan_results(self, scan_result: Dict[str, Any]):
        """Store scan results in the knowledge graph."""
        if not self.graph_store:
            return
        
        try:
            repo_metadata = {
                'repo_path': str(self.repo_path),
                'repo_reference': self.repo_reference,
                'repo_slug': self.repo_slug,
            }
            # Create scan node
            scan_query = """
            CREATE (scan:SecurityScan {
                id: $scan_id,
                timestamp: $timestamp,
                total_vulnerabilities: $total_vulnerabilities,
                repo_path: $repo_path,
                repo_reference: $repo_reference,
                repo_slug: $repo_slug,
                layer: 'security'
            })
            RETURN scan
            """
            
            self.graph_store.query(scan_query, {
                'scan_id': scan_result['scan_id'],
                'timestamp': scan_result['timestamp'],
                'total_vulnerabilities': scan_result['total_vulnerabilities'],
                **repo_metadata,
            })
            
            # Create vulnerability nodes and link to files
            for vuln in scan_result['vulnerabilities']:
                rel_path = self._relative_file_path(vuln.get('file_path', ''))
                file_match_clause = self._build_file_match_clause()
                vuln_query = """
                MERGE (v:Vulnerability {
                    rule_id: $rule_id,
                    file_path: $file_path,
                    line: $line
                })
                SET v.severity = $severity,
                    v.category = $category,
                    v.message = $message,
                    v.last_seen = $timestamp,
                    v.repo_path = $repo_path,
                    v.repo_reference = $repo_reference,
                    v.repo_slug = $repo_slug,
                    v.layer = 'security'
                WITH v
                MATCH (scan:SecurityScan {id: $scan_id})
                MERGE (scan)-[fs:FOUND]->(v)
                SET fs.layer = 'security'
                WITH v
                {file_match_clause}
                MERGE (file)-[hv:HAS_VULNERABILITY]->(v)
                SET hv.layer = 'security'
                """.replace("{file_match_clause}", file_match_clause)

                params = {
                    'scan_id': scan_result['scan_id'],
                    'rule_id': vuln.get('rule_id', 'unknown'),
                    'file_path': rel_path,
                    'line': vuln.get('line', 0),
                    'severity': vuln.get('severity', 'unknown'),
                    'category': vuln.get('category', 'unknown'),
                    'message': vuln.get('message', ''),
                    'timestamp': scan_result['timestamp'],
                    **repo_metadata,
                }
                file_identifier = self._file_node_id(rel_path)
                if file_identifier:
                    params['file_id'] = file_identifier
                
                self.graph_store.query(vuln_query, params)
            
            logger.info(f"Stored scan results in graph: {scan_result['scan_id']}")
        except Exception as exc:
            logger.error(f"Failed to store scan results in graph: {exc}")

    def _relative_file_path(self, file_path: str) -> str:
        """Return repository-relative POSIX path for a finding."""
        try:
            candidate = Path(file_path).resolve()
            relative = candidate.relative_to(self._repo_root)
            return relative.as_posix()
        except Exception:
            # Fall back to provided value (Semgrep sometimes emits repo-relative already)
            return file_path.replace("\\", "/")

    def _file_node_id(self, relative_path: str) -> Optional[str]:
        if not self.repo_slug or not relative_path:
            return None
        return f"{self.repo_slug}::file::{relative_path}"

    def _build_file_match_clause(self) -> str:
        if self.repo_slug:
            return "MATCH (file:File {id: $file_id})"
        return "MATCH (file:File {path: $file_path})"

    def get_scan_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent scan history."""
        return self.scan_history[-limit:]

    def get_vulnerability_trends(self) -> Dict[str, Any]:
        """
        Analyze vulnerability trends over time.
        
        Returns:
            Trend analysis with counts over time
        """
        if len(self.scan_history) < 2:
            return {'error': 'Insufficient scan history'}
        
        trends = {
            'total_scans': len(self.scan_history),
            'first_scan': self.scan_history[0]['timestamp'],
            'latest_scan': self.scan_history[-1]['timestamp'],
            'current_vulnerabilities': self.scan_history[-1]['total_vulnerabilities'],
            'previous_vulnerabilities': self.scan_history[-2]['total_vulnerabilities'],
            'trend': 'improving' if self.scan_history[-1]['total_vulnerabilities'] < 
                     self.scan_history[-2]['total_vulnerabilities'] else 'worsening',
            'history': [
                {
                    'timestamp': scan['timestamp'],
                    'total': scan['total_vulnerabilities'],
                    'critical': scan['severity_breakdown'].get('critical', 0),
                    'high': scan['severity_breakdown'].get('high', 0)
                }
                for scan in self.scan_history
            ]
        }
        
        return trends

    def schedule_daily_scans(self, time_str: str = "02:00"):
        """
        Schedule daily security scans.
        
        Args:
            time_str: Time to run scans in HH:MM format (24-hour)
        """
        schedule.every().day.at(time_str).do(self.run_full_scan)
        logger.info(f"Scheduled daily security scans at {time_str}")

    def start_scheduler(self):
        """Start the background scheduler (blocking)."""
        self.is_running = True
        logger.info("Starting security scanner scheduler")
        
        while self.is_running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

    def stop_scheduler(self):
        """Stop the background scheduler."""
        self.is_running = False
        logger.info("Stopped security scanner scheduler")

    def get_critical_vulnerabilities(self) -> List[Dict[str, Any]]:
        """Get all critical and high severity vulnerabilities from latest scan."""
        if not self.scan_history:
            return []
        
        latest_scan = self.scan_history[-1]
        critical = [
            v for v in latest_scan['vulnerabilities']
            if v.get('severity', '').lower() in ['critical', 'high']
        ]
        
        return critical
