# executor/tools/email/draft_email.py

from langchain_core.tools import tool

from email.message import EmailMessage

from ._email_client import EmailClient



@tool
def draft_email(
    to:str,
    subject:str,
    body:str
):
    """
    Create an email draft.
    """

    client=EmailClient()


    msg=EmailMessage()

    msg["From"]=client.config.username
    msg["To"]=to
    msg["Subject"]=subject

    msg.set_content(body)


    imap=client.select_folder(
        "[Gmail]/Drafts"
    )


    imap.append(
        "[Gmail]/Drafts",
        "\\Draft",
        None,
        msg.as_bytes()
    )


    return {
        "status":"draft_created"
    }