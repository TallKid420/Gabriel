from langchain_core.tools import tool

from ._email_client import EmailClient

from email.message import EmailMessage



@tool
def reply_email(
    email_id:str,
    body:str
):

    """
    Reply to an email.
    """

    client=EmailClient()

    original=client.fetch_email(
        email_id
    )


    msg=EmailMessage()

    msg["From"]=client.config.username
    msg["To"]=original["From"]
    msg["Subject"]="Re: "+client.decode(
        original["Subject"]
    )

    msg.set_content(body)


    client.connect_smtp().send_message(
        msg
    )


    return "Reply sent"