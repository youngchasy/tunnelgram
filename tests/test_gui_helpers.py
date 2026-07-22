from tunnelgram.gui import App


def test_clean_sing_box_output_removes_ansi_sequences() -> None:
    raw = "\x1b[31mERROR\x1b[0m example"
    assert App.clean_sing_box_output(raw) == "ERROR example"
