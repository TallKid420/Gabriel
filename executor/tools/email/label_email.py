# executor/tools/email/label_email.py

from langchain_core.tools import tool

from ._email_client import EmailClient


@tool
def label_email(
    email_id: str,
    label: str
):
    """
    Add a label to an email.
    """

    client = EmailClient()

    imap = client.select_folder()

    imap.store(
        email_id,
        "+X-GM-LABELS",
        label
    )


    return {
        "status": "label_added",
        "label": label,
        "email_id": email_id
    }