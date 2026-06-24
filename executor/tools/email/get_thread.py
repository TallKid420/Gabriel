# executor/tools/email/get_thread.py

from langchain_core.tools import tool

from ._email_client import EmailClient



@tool
def get_thread(email_id:str):
    """
    Retrieve related emails in a thread.
    """

    client=EmailClient()

    original=client.fetch_email(
        email_id
    )


    subject = client.decode(
        original["Subject"]
    )


    imap=client.select_folder()


    status,data = imap.search(
        None,
        f'(SUBJECT "{subject}")'
    )


    emails=[]


    for item in data[0].split():

        msg=client.fetch_email(
            item
        )


        emails.append({

            "id":item.decode(),

            "from":msg["From"],

            "subject":
                client.decode(
                    msg["Subject"]
                ),

            "date":
                msg["Date"]

        })


    return emails