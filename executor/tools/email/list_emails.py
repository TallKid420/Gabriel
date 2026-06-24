from langchain_core.tools import tool

from ._email_client import EmailClient



@tool
def list_emails(limit:int=10):
    """
    List recent emails.
    """

    client = EmailClient()

    imap = client.select_folder()

    status,data = imap.search(
        None,
        "ALL"
    )

    ids = data[0].split()

    results=[]


    for email_id in ids[-limit:]:

        msg = client.fetch_email(email_id)

        results.append({

            "id": email_id.decode(),

            "subject":
                client.decode(
                    msg["Subject"]
                ),

            "from":
                msg["From"],

            "date":
                msg["Date"]

        })


    return results