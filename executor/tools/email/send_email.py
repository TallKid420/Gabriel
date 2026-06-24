from langchain_core.tools import tool

from email.message import EmailMessage

from ._email_client import EmailClient



@tool
def send_email(
    to:str,
    subject:str,
    body:str
):

    """
    Send email.
    """

    client=EmailClient()

    msg=EmailMessage()

    msg["From"]=client.config.username
    msg["To"]=to
    msg["Subject"]=subject

    msg.set_content(body)


    smtp=client.connect_smtp()


    smtp.send_message(msg)


    return "Email sent"