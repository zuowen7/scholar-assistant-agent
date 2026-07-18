from src.translator.context import extract_document_context


def test_body_paragraph_is_not_misclassified_as_title() -> None:
    text = (
        "Large language models can support academic writing, but their suggestions "
        "must remain traceable to evidence.\n\n"
        "Reliable research software should preserve user intent."
    )

    assert extract_document_context(text) == ""


def test_short_heading_is_kept_as_document_title() -> None:
    text = "Reliable Academic Translation\n\nAbstract\nA sufficiently long abstract belongs here."

    assert extract_document_context(text).startswith("标题: Reliable Academic Translation")
