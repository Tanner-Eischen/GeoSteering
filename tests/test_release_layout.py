"""Document behavior regression for the observed orphaned limitations heading."""
from pypdf import PdfReader

from tools.run_case_study import run_case_study


def test_section_heading_and_first_body_paragraph_share_a_page(tmp_path):
    pdf = run_case_study(tmp_path / 'layout-case')
    pages = [page.extract_text() or '' for page in PdfReader(pdf).pages]
    matches = [text for text in pages if 'Assumptions and limitations' in text]
    assert len(matches) == 1
    after_heading = matches[0].split('Assumptions and limitations', 1)[1]
    assert 'Synthetic calibration: GR' in after_heading
    assert 'real gamma-ray inversion' in after_heading
