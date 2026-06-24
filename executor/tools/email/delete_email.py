# executor/tools/email/delete_email.py

from langchain_core.tools import tool

from ._email_client import EmailClient


@tool
def delete_email(email_id: str):
    """
    Permanently delete an email.
    """

    client = EmailClient()

    imap = client.select_folder()

    imap.store(
        email_id,
        "+FLAGS",
        "\\Deleted"
    )

    imap.expunge()

    return {
        "status": "deleted",
        "email_id": email_id
    }
