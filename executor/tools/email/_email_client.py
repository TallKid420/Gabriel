# executor/tools/email/_email_client.py

from __future__ import annotations

import imaplib
import smtplib
import email
from email.message import EmailMessage
from email.header import decode_header
from typing import Any

from config.runtime import tool_manager



class EmailClient:

    def __init__(self):

        self.config = tool_manager.get_email()

        self.imap = None
        self.smtp = None


    # ======================
    # IMAP
    # ======================

    def connect_imap(self):

        if self.imap:
            return self.imap


        if self.config.use_ssl:

            self.imap = imaplib.IMAP4_SSL(
                self.config.imap_host,
                self.config.imap_port
            )

        else:

            self.imap = imaplib.IMAP4(
                self.config.imap_host,
                self.config.imap_port
            )


        self.imap.login(
            self.config.username,
            self.config.password
        )


        return self.imap



    def select_folder(
        self,
        folder=None
    ):

        imap = self.connect_imap()

        folder = folder or self.config.default_folder

        imap.select(folder)

        return imap



    def fetch_email(
        self,
        email_id
    ):

        imap = self.select_folder()

        status, data = imap.fetch(
            email_id,
            "(RFC822)"
        )

        if status != "OK":
            return None


        raw = data[0][1]

        return email.message_from_bytes(raw)



    def decode(self, value):

        if not value:
            return ""


        decoded = decode_header(value)[0]

        if isinstance(decoded[0], bytes):

            return decoded[0].decode(
                decoded[1] or "utf-8",
                errors="ignore"
            )

        return decoded[0]



    # ======================
    # SMTP
    # ======================


    def connect_smtp(self):

        if self.smtp:
            return self.smtp


        if self.config.use_ssl:

            self.smtp = smtplib.SMTP_SSL(
                self.config.smtp_host,
                self.config.smtp_port
            )

        else:

            self.smtp = smtplib.SMTP(
                self.config.smtp_host,
                self.config.smtp_port
            )


        self.smtp.login(
            self.config.username,
            self.config.password
        )


        return self.smtp
    
    def list_folders(self):
        self.imap.list()


    def create_folder(self,name):
        self.imap.create(name)


    def get_labels(self):
        self.imap.list()