"""docs/testing-quality.md table is generated from real results (idea 49)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("report_qa", ROOT / "scripts/report_qa.py")
report_qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report_qa)

JUNIT = """<testsuites><testsuite>
<testcase classname="tests.test_reminders.X" name="a" time="0.1"/>
<testcase classname="tests.test_reminders.X" name="b" time="0.1"><failure/></testcase>
<testcase classname="tests.test_webread.Y" name="c" time="0.1"><skipped/></testcase>
</testsuite></testsuites>"""


def test_table_and_doc_update(tmp_path):
    junit = tmp_path / "t.xml"
    junit.write_text(JUNIT)
    table = report_qa.markdown_table(report_qa.report(junit), {"mutations": [{"detected": True}, {"detected": False}]}, "2026-11-23")
    assert "| scheduling | 1 | 1 | 0 |" in table and "| **Total** | **1** | **1** | **1** |" in table
    assert "**1 / 2**" in table
    doc = tmp_path / "doc.md"
    doc.write_text(f"intro\n{report_qa.START}\nold\n{report_qa.END}\nfin\n")
    report_qa.update_doc(doc, table)
    text = doc.read_text()
    assert "old" not in text and text.startswith("intro") and text.endswith("fin\n") and "scheduling" in text


def test_repository_doc_has_the_markers():
    text = (ROOT / "docs/testing-quality.md").read_text()
    assert report_qa.START in text and report_qa.END in text
    assert "1 753 tests" in text  # the October snapshot stays as history, below the current table header
