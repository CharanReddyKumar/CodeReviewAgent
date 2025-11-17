"""Tests for tools/static_analysis.py - Complete coverage"""
import pytest
from tools.static_analysis import (
    parse_patch,
    detect_style_issues,
    detect_security_issues,
    AddedLine,
    Issue,
    PATCH_HEADER_RE,
    SECURITY_PATTERNS,
)


class TestParsePatch:
    """Tests for parse_patch function."""

    def test_parse_patch_simple_addition(self):
        """Test parsing simple addition."""
        patch = """@@ -1,2 +1,3 @@
 def hello():
     return 'world'
+    print('added line')
"""
        lines = parse_patch("test.py", patch)
        assert len(lines) == 1
        assert lines[0].file_path == "test.py"
        assert lines[0].line_no == 3
        assert lines[0].content == "    print('added line')"

    def test_parse_patch_multiple_additions(self):
        """Test parsing multiple additions."""
        patch = """@@ -1,2 +1,4 @@
 def hello():
+    x = 1
     return 'world'
+    y = 2
"""
        lines = parse_patch("test.py", patch)
        assert len(lines) == 2
        assert lines[0].line_no == 2
        assert lines[1].line_no == 4

    def test_parse_patch_with_deletions(self):
        """Test parsing patch with deletions."""
        patch = """@@ -1,3 +1,2 @@
 def hello():
-    old_line = 1
+    new_line = 1
     return 'world'
"""
        lines = parse_patch("test.py", patch)
        assert len(lines) == 1
        assert lines[0].content == "    new_line = 1"

    def test_parse_patch_empty(self):
        """Test parsing empty patch."""
        lines = parse_patch("test.py", "")
        assert len(lines) == 0

    def test_parse_patch_no_additions(self):
        """Test parsing patch with no additions."""
        patch = """@@ -1,2 +1,1 @@
 def hello():
-    return 'world'
"""
        lines = parse_patch("test.py", patch)
        assert len(lines) == 0

    def test_parse_patch_multiple_hunks(self):
        """Test parsing patch with multiple hunks."""
        patch = """@@ -1,2 +1,3 @@
 def hello():
+    x = 1
     return 'world'
@@ -10,2 +11,3 @@
 def goodbye():
+    y = 2
     return 'bye'
"""
        lines = parse_patch("test.py", patch)
        assert len(lines) == 2
        assert lines[0].line_no == 2
        assert lines[1].line_no == 12

    def test_parse_patch_ignore_no_newline(self):
        """Test parsing patch ignores 'No newline' marker."""
        patch = """@@ -1,1 +1,2 @@
 def hello():
+    return 'world'
\\ No newline at end of file
"""
        lines = parse_patch("test.py", patch)
        assert len(lines) == 1


class TestDetectStyleIssues:
    """Tests for detect_style_issues function."""

    def test_detect_long_line(self):
        """Test detecting lines exceeding 120 characters."""
        lines = [
            AddedLine("test.py", 10, "x = " + "a" * 130)
        ]
        issues = detect_style_issues(lines)
        assert len(issues) == 1
        assert issues[0].rule_id == "STYLE_LONG_LINE"
        assert issues[0].severity == "low"

    def test_detect_trailing_whitespace(self):
        """Test detecting trailing whitespace."""
        lines = [
            AddedLine("test.py", 10, "x = 1   ")
        ]
        issues = detect_style_issues(lines)
        assert len(issues) == 1
        assert issues[0].rule_id == "STYLE_TRAILING_WHITESPACE"

    def test_detect_todo_comment(self):
        """Test detecting TODO comments."""
        lines = [
            AddedLine("test.py", 10, "# TODO: fix this")
        ]
        issues = detect_style_issues(lines)
        assert len(issues) == 1
        assert issues[0].rule_id == "STYLE_TODO"
        assert issues[0].severity == "medium"

    def test_detect_fixme_comment(self):
        """Test detecting FIXME comments."""
        lines = [
            AddedLine("test.py", 10, "# FIXME: broken code")
        ]
        issues = detect_style_issues(lines)
        assert len(issues) == 1
        assert issues[0].rule_id == "STYLE_TODO"

    def test_detect_multiple_issues_same_line(self):
        """Test detecting multiple issues on same line."""
        lines = [
            AddedLine("test.py", 10, "# TODO: " + "a" * 120 + "  ")
        ]
        issues = detect_style_issues(lines)
        assert len(issues) == 3  # long line, trailing whitespace, TODO

    def test_detect_no_issues(self):
        """Test no issues detected for clean code."""
        lines = [
            AddedLine("test.py", 10, "x = 1")
        ]
        issues = detect_style_issues(lines)
        assert len(issues) == 0


class TestDetectSecurityIssues:
    """Tests for detect_security_issues function."""

    def test_detect_eval_usage(self):
        """Test detecting eval() usage."""
        lines = [
            AddedLine("test.py", 10, "result = eval(user_input)")
        ]
        issues = detect_security_issues(lines)
        assert len(issues) == 1
        assert issues[0].rule_id == "SEC_EVAL"
        assert issues[0].severity == "high"

    def test_detect_exec_usage(self):
        """Test detecting exec() usage."""
        lines = [
            AddedLine("test.py", 10, "exec(user_code)")
        ]
        issues = detect_security_issues(lines)
        assert len(issues) == 1
        assert issues[0].rule_id == "SEC_EXEC"
        assert issues[0].severity == "high"

    def test_detect_os_system(self):
        """Test detecting os.system usage."""
        lines = [
            AddedLine("test.py", 10, "os.system('rm -rf /')")
        ]
        issues = detect_security_issues(lines)
        assert len(issues) == 1
        assert issues[0].rule_id == "SEC_OS_SYSTEM"
        assert issues[0].severity == "medium"

    def test_detect_subprocess_shell_true(self):
        """Test detecting subprocess with shell=True."""
        lines = [
            AddedLine("test.py", 10, "subprocess.call(cmd, shell=True)")
        ]
        issues = detect_security_issues(lines)
        assert len(issues) == 1
        assert issues[0].rule_id == "SEC_SHELL_TRUE"

    def test_detect_pickle_loads(self):
        """Test detecting pickle.loads usage."""
        lines = [
            AddedLine("test.py", 10, "data = pickle.loads(untrusted)")
        ]
        issues = detect_security_issues(lines)
        assert len(issues) == 1
        assert issues[0].rule_id == "SEC_PICKLE_LOADS"

    def test_detect_no_security_issues(self):
        """Test no security issues in safe code."""
        lines = [
            AddedLine("test.py", 10, "x = 1 + 2")
        ]
        issues = detect_security_issues(lines)
        assert len(issues) == 0

    def test_detect_first_match_only(self):
        """Test only first matching pattern is reported per line."""
        # Line has eval, but only one issue should be reported
        lines = [
            AddedLine("test.py", 10, "eval(exec(code))")
        ]
        issues = detect_security_issues(lines)
        assert len(issues) == 1  # Only eval is detected (first pattern)


class TestPatternMatching:
    """Tests for pattern matching."""

    def test_patch_header_regex(self):
        """Test PATCH_HEADER_RE regex."""
        match = PATCH_HEADER_RE.match("@@ -10,5 +15,7 @@")
        assert match is not None
        assert match.group(1) == "15"
        assert match.group(2) == "7"

    def test_patch_header_regex_no_count(self):
        """Test PATCH_HEADER_RE with no line count."""
        match = PATCH_HEADER_RE.match("@@ -10 +15 @@")
        assert match is not None
        assert match.group(1) == "15"

    def test_security_patterns_exist(self):
        """Test security patterns are defined."""
        assert len(SECURITY_PATTERNS) > 0
        assert all(len(p) == 3 for p in SECURITY_PATTERNS)
