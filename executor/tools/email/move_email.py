# executor/tools/email/move_email.py

from langchain_core.tools import tool

from ._email_client import EmailClient



@tool
def move_email(
    email_id:str,
    destination:str
):
    """
    Move email to another folder.
    """

    client=EmailClient()

    imap=client.select_folder()


    result = imap.copy(
        email_id,
        destination
    )


    if result[0] == "OK":

        imap.store(
            email_id,
            "+FLAGS",
            "\\Deleted"
        )

        imap.expunge()



    return {
        "status":"moved",
        "destination":destination,
        "email_id":email_id
    }