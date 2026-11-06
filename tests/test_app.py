from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_renders_base_case_without_errors():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    assert any("Recommendation" in h.value for h in at.subheader)


def test_app_what_if_rerun():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.slider[0].set_value(0.70)
    at.select_slider[0].set_value(1000)
    at.run()
    assert not at.exception
    assert any("what-if" in i.value for i in at.info)
