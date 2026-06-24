# executor/tools/email/mark_email.py

from langchain_core.tools import tool

from ._email_client import EmailClient



@tool
def mark_email(
    email_id:str,
    read:bool=True
):
    """
    Mark email as read or unread.
    """

    client=EmailClient()

    imap=client.select_folder()


    if read:

        imap.store(
            email_id,
            "+FLAGS",
            "\\Seen"
        )

    else:

        imap.store(
            email_id,
            "-FLAGS",
            "\\Seen"
        )


    return {
        "email_id":email_id,
        "read":read
    }