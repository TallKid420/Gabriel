from langchain_core.tools import tool

from ._email_client import EmailClient



@tool
def search_emails(query:str):

    """
    Search emails.
    """

    client=EmailClient()

    imap=client.select_folder()


    status,data=imap.search(
        None,
        f'(TEXT "{query}")'
    )


    return [
        x.decode()
        for x in data[0].split()
    ]