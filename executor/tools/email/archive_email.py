# executor/tools/email/archive_email.py

from langchain_core.tools import tool

from ._email_client import EmailClient


@tool
def archive_email(email_id: str):
    """
    Archive an email.
    Removes it from inbox.
    """

    client = EmailClient()

    imap = client.select_folder()

    imap.store(
        email_id,
        "-FLAGS",
        "\\Inbox"
    )

    return {
        "status": "archived",
        "email_id": email_id
    }