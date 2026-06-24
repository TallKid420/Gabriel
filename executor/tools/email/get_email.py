from langchain_core.tools import tool

from ._email_client import EmailClient



@tool
def get_email(email_id:str):
    """
    Get full email contents.
    """

    client=EmailClient()

    msg=client.fetch_email(email_id)


    body=""

    if msg.is_multipart():

        for part in msg.walk():

            if part.get_content_type()=="text/plain":

                body += part.get_payload(
                    decode=True
                ).decode(
                    errors="ignore"
                )

    else:

        body=msg.get_payload(
            decode=True
        ).decode(
            errors="ignore"
        )


    return {

        "from":msg["From"],
        "subject":client.decode(msg["Subject"]),
        "body":body

    }