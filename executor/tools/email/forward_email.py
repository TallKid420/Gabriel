from langchain_core.tools import tool

from ._email_client import EmailClient

from email.message import EmailMessage



@tool
def forward_email(
    email_id:str,
    to:str
):

    client=EmailClient()

    original=client.fetch_email(
        email_id
    )


    msg=EmailMessage()

    msg["From"]=client.config.username
    msg["To"]=to
    msg["Subject"]="Fwd: "+client.decode(
        original["Subject"]
    )

    msg.set_content(
        original.as_string()
    )


    client.connect_smtp().send_message(
        msg
    )


    return "Forwarded"