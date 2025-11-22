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

logger = logging.getLogger(__name__)


class SecurityScanner:
    """
    Proactive security scanner that runs daily repo-wide scans.
    Integrates with SAST tools and stores results in the knowledge graph.
    """

    def __init__(self, repo_path: Path, graph_store: Optional[GraphStore] = None):
        self.repo_path = Path(repo_path)
        self.graph_store = graph_store
        self.semgrep_agent = SemgrepAgent(repo_path)
        self.scan_history: List[Dict[str, Any]] = []
        self.is_running = False

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
            # Create scan node
            scan_query = """
            CREATE (scan:SecurityScan {
                id: $scan_id,
                timestamp: $timestamp,
                total_vulnerabilities: $total_vulnerabilities
            })
            RETURN scan
            """
            
            self.graph_store.query(scan_query, {
                'scan_id': scan_result['scan_id'],
                'timestamp': scan_result['timestamp'],
                'total_vulnerabilities': scan_result['total_vulnerabilities']
            })
            
            # Create vulnerability nodes and link to files
            for vuln in scan_result['vulnerabilities']:
                vuln_query = """
                MERGE (v:Vulnerability {
                    rule_id: $rule_id,
                    file_path: $file_path,
                    line: $line
                })
                SET v.severity = $severity,
                    v.category = $category,
                    v.message = $message,
                    v.last_seen = $timestamp
                WITH v
                MATCH (scan:SecurityScan {id: $scan_id})
                MERGE (scan)-[:FOUND]->(v)
                WITH v
                MATCH (file:File {path: $file_path})
                MERGE (file)-[:HAS_VULNERABILITY]->(v)
                """
                
                self.graph_store.query(vuln_query, {
                    'scan_id': scan_result['scan_id'],
                    'rule_id': vuln.get('rule_id', 'unknown'),
                    'file_path': vuln.get('file_path', ''),
                    'line': vuln.get('line', 0),
                    'severity': vuln.get('severity', 'unknown'),
                    'category': vuln.get('category', 'unknown'),
                    'message': vuln.get('message', ''),
                    'timestamp': scan_result['timestamp']
                })
            
            logger.info(f"Stored scan results in graph: {scan_result['scan_id']}")
        except Exception as exc:
            logger.error(f"Failed to store scan results in graph: {exc}")

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
