# services/pdf_reader_service.py

from io import BytesIO
import logging
import threading
from typing import Any, Dict, List, Optional, Union
import os
from pathlib import Path
from pdfminer.high_level import extract_text
from pdfminer.layout import LAParams
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from modules.utilities.logging_manager import setup_logging
from modules.utilities.config_loader import ConfigLoader
from modules.security.encryption_manager import EncryptionManager
from modules.security.authentication import AuthenticationManager


class PDFReaderServiceError(Exception):
    """Custom exception for PDFReaderService-related errors."""
    pass


class PDFReaderService:
    """
    Provides PDF reading and manipulation capabilities, including text extraction,
    metadata retrieval, page manipulation, and PDF creation. Utilizes libraries
    like PDFMiner, PyPDF2, and ReportLab to ensure comprehensive PDF handling.
    Ensures secure handling of files and configurations.
    """

    def __init__(self):
        """
        Initializes the PDFReaderService with necessary configurations and authentication.
        """
        self.logger = setup_logging('PDFReaderService')
        self.config_loader = ConfigLoader()
        self.encryption_manager = EncryptionManager()
        self.auth_manager = AuthenticationManager()
        self.lock = threading.Lock()
        self.logger.info("PDFReaderService initialized successfully.")

    def extract_text_from_pdf(self, pdf_path: str, password: Optional[str] = None) -> Optional[str]:
        """
        Extracts all text from a specified PDF file.

        Args:
            pdf_path (str): The file path to the PDF.
            password (Optional[str], optional): The password for encrypted PDFs. Defaults to None.

        Returns:
            Optional[str]: The extracted text, or None if extraction fails.
        """
        try:
            self.logger.debug(f"Extracting text from PDF '{pdf_path}' with password '{password}'.")
            if not os.path.exists(pdf_path):
                self.logger.error(f"PDF file '{pdf_path}' does not exist.")
                return None
            text = extract_text(pdf_path, password=password, laparams=LAParams())
            self.logger.info(f"Text extracted successfully from '{pdf_path}'.")
            return text
        except Exception as e:
            self.logger.error(f"Error extracting text from PDF '{pdf_path}': {e}", exc_info=True)
            return None

    def get_pdf_metadata(self, pdf_path: str, password: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves metadata from a specified PDF file.

        Args:
            pdf_path (str): The file path to the PDF.
            password (Optional[str], optional): The password for encrypted PDFs. Defaults to None.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing metadata, or None if retrieval fails.
        """
        try:
            self.logger.debug(f"Retrieving metadata from PDF '{pdf_path}' with password '{password}'.")
            if not os.path.exists(pdf_path):
                self.logger.error(f"PDF file '{pdf_path}' does not exist.")
                return None
            reader = PdfReader(pdf_path)
            if reader.is_encrypted:
                if password:
                    reader.decrypt(password)
                else:
                    self.logger.error("PDF is encrypted and no password was provided.")
                    return None
            metadata = reader.metadata
            metadata_dict = {key[1:]: value for key, value in metadata.items()}  # Remove leading '/'
            self.logger.info(f"Metadata retrieved successfully from '{pdf_path}': {metadata_dict}")
            return metadata_dict
        except Exception as e:
            self.logger.error(f"Error retrieving metadata from PDF '{pdf_path}': {e}", exc_info=True)
            return None

    def split_pdf(self, pdf_path: str, pages: List[int], output_path: str, password: Optional[str] = None) -> bool:
        """
        Splits a PDF into multiple PDFs based on specified page numbers.

        Args:
            pdf_path (str): The file path to the original PDF.
            pages (List[int]): A list of page numbers to include in the split PDF.
            output_path (str): The file path for the split PDF.
            password (Optional[str], optional): The password for encrypted PDFs. Defaults to None.

        Returns:
            bool: True if the PDF is split successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Splitting PDF '{pdf_path}' into pages {pages} into '{output_path}' with password '{password}'.")
            if not os.path.exists(pdf_path):
                self.logger.error(f"PDF file '{pdf_path}' does not exist.")
                return False
            reader = PdfReader(pdf_path)
            if reader.is_encrypted:
                if password:
                    reader.decrypt(password)
                else:
                    self.logger.error("PDF is encrypted and no password was provided.")
                    return False
            writer = PdfWriter()
            for page_num in pages:
                if page_num < 1 or page_num > len(reader.pages):
                    self.logger.warning(f"Page number {page_num} is out of range for PDF '{pdf_path}'.")
                    continue
                writer.add_page(reader.pages[page_num - 1])
            with open(output_path, 'wb') as f_out:
                writer.write(f_out)
            self.logger.info(f"PDF split successfully into '{output_path}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error splitting PDF '{pdf_path}': {e}", exc_info=True)
            return False

    def merge_pdfs(self, pdf_paths: List[str], output_path: str, password: Optional[str] = None) -> bool:
        """
        Merges multiple PDFs into a single PDF.

        Args:
            pdf_paths (List[str]): A list of file paths to the PDFs to merge.
            output_path (str): The file path for the merged PDF.
            password (Optional[str], optional): The password for encrypted PDFs. Defaults to None.

        Returns:
            bool: True if the PDFs are merged successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Merging PDFs {pdf_paths} into '{output_path}' with password '{password}'.")
            writer = PdfWriter()
            for pdf_path in pdf_paths:
                if not os.path.exists(pdf_path):
                    self.logger.warning(f"PDF file '{pdf_path}' does not exist. Skipping.")
                    continue
                reader = PdfReader(pdf_path)
                if reader.is_encrypted:
                    if password:
                        reader.decrypt(password)
                    else:
                        self.logger.error(f"PDF '{pdf_path}' is encrypted and no password was provided.")
                        return False
                for page in reader.pages:
                    writer.add_page(page)
            with open(output_path, 'wb') as f_out:
                writer.write(f_out)
            self.logger.info(f"PDFs merged successfully into '{output_path}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error merging PDFs into '{output_path}': {e}", exc_info=True)
            return False

    def add_watermark(self, pdf_path: str, watermark_text: str, output_path: str, position: str = 'center', opacity: float = 0.3, password: Optional[str] = None) -> bool:
        """
        Adds a watermark to each page of a PDF.

        Args:
            pdf_path (str): The file path to the original PDF.
            watermark_text (str): The text to use as the watermark.
            output_path (str): The file path for the watermarked PDF.
            position (str, optional): The position of the watermark ('center', 'top-left', 'top-right', 'bottom-left', 'bottom-right'). Defaults to 'center'.
            opacity (float, optional): The opacity of the watermark (0.0 to 1.0). Defaults to 0.3.
            password (Optional[str], optional): The password for encrypted PDFs. Defaults to None.

        Returns:
            bool: True if the watermark is added successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Adding watermark to PDF '{pdf_path}' with text '{watermark_text}' at position '{position}' and opacity '{opacity}'.")
            if not os.path.exists(pdf_path):
                self.logger.error(f"PDF file '{pdf_path}' does not exist.")
                return False

            # Create a temporary PDF with the watermark
            watermark_pdf = self._create_watermark_pdf(watermark_text, position, opacity)
            if not watermark_pdf:
                self.logger.error("Failed to create watermark PDF.")
                return False

            # Merge the watermark with the original PDF
            reader = PdfReader(pdf_path)
            if reader.is_encrypted:
                if password:
                    reader.decrypt(password)
                else:
                    self.logger.error("PDF is encrypted and no password was provided.")
                    return False
            watermark_reader = PdfReader(watermark_pdf)
            watermark_page = watermark_reader.pages[0]

            writer = PdfWriter()
            for page_num, page in enumerate(reader.pages, start=1):
                page.merge_page(watermark_page)
                writer.add_page(page)
                self.logger.debug(f"Watermark added to page {page_num}.")

            with open(output_path, 'wb') as f_out:
                writer.write(f_out)
            self.logger.info(f"Watermark added successfully to '{output_path}'.")
            os.remove(watermark_pdf)
            self.logger.debug(f"Temporary watermark PDF '{watermark_pdf}' removed.")
            return True
        except Exception as e:
            self.logger.error(f"Error adding watermark to PDF '{pdf_path}': {e}", exc_info=True)
            return False

    def _create_watermark_pdf(self, text: str, position: str, opacity: float) -> Optional[str]:
        """
        Creates a PDF file containing the watermark text.

        Args:
            text (str): The watermark text.
            position (str): The position of the watermark.
            opacity (float): The opacity of the watermark.

        Returns:
            Optional[str]: The file path to the watermark PDF, or None if creation fails.
        """
        try:
            self.logger.debug(f"Creating watermark PDF with text '{text}', position '{position}', and opacity '{opacity}'.")
            watermark_path = Path('./temp_watermark.pdf')
            c = canvas.Canvas(str(watermark_path), pagesize=letter)
            c.setFillAlpha(opacity)
            c.setFont("Helvetica", 40)

            width, height = letter
            text_width = c.stringWidth(text, "Helvetica", 40)

            if position == 'center':
                x = (width - text_width) / 2
                y = height / 2
            elif position == 'top-left':
                x = 50
                y = height - 50
            elif position == 'top-right':
                x = width - text_width - 50
                y = height - 50
            elif position == 'bottom-left':
                x = 50
                y = 50
            elif position == 'bottom-right':
                x = width - text_width - 50
                y = 50
            else:
                x = (width - text_width) / 2
                y = height / 2

            c.drawString(x, y, text)
            c.save()
            self.logger.debug(f"Watermark PDF created at '{watermark_path}'.")
            return str(watermark_path)
        except Exception as e:
            self.logger.error(f"Error creating watermark PDF: {e}", exc_info=True)
            return None

    def create_pdf(self, text: str, output_path: str, font: str = 'Helvetica', font_size: int = 12, page_size: str = 'letter') -> bool:
        """
        Creates a new PDF file from the provided text.

        Args:
            text (str): The text content to include in the PDF.
            output_path (str): The file path for the created PDF.
            font (str, optional): The font to use. Defaults to 'Helvetica'.
            font_size (int, optional): The font size to use. Defaults to 12.
            page_size (str, optional): The page size ('letter', 'A4'). Defaults to 'letter'.

        Returns:
            bool: True if the PDF is created successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Creating PDF at '{output_path}' with font '{font}', font size '{font_size}', and page size '{page_size}'.")
            if page_size.lower() == 'a4':
                page_dimensions = (595.27, 841.89)  # A4 size in points
            else:
                page_dimensions = letter

            c = canvas.Canvas(output_path, pagesize=page_dimensions)
            c.setFont(font, font_size)
            text_object = c.beginText(40, page_dimensions[1] - 40)
            for line in text.split('\n'):
                text_object.textLine(line)
            c.drawText(text_object)
            c.save()
            self.logger.info(f"PDF created successfully at '{output_path}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error creating PDF at '{output_path}': {e}", exc_info=True)
            return False

    def add_page_numbers(self, pdf_path: str, output_path: str, password: Optional[str] = None) -> bool:
        """
        Adds page numbers to each page of a PDF.

        Args:
            pdf_path (str): The file path to the original PDF.
            output_path (str): The file path for the PDF with page numbers.
            password (Optional[str], optional): The password for encrypted PDFs. Defaults to None.

        Returns:
            bool: True if page numbers are added successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Adding page numbers to PDF '{pdf_path}' into '{output_path}' with password '{password}'.")
            if not os.path.exists(pdf_path):
                self.logger.error(f"PDF file '{pdf_path}' does not exist.")
                return False

            reader = PdfReader(pdf_path)
            if reader.is_encrypted:
                if password:
                    reader.decrypt(password)
                else:
                    self.logger.error("PDF is encrypted and no password was provided.")
                    return False

            writer = PdfWriter()
            for i, page in enumerate(reader.pages, start=1):
                packet = BytesIO()
                can = canvas.Canvas(packet, pagesize=page.mediabox)
                can.setFont("Helvetica", 12)
                can.drawString(page.mediabox.width - 50, 20, f"Page {i}")
                can.save()

                packet.seek(0)
                watermark = PdfReader(packet)
                page.merge_page(watermark.pages[0])
                writer.add_page(page)
                self.logger.debug(f"Page number {i} added.")

            with open(output_path, 'wb') as f_out:
                writer.write(f_out)
            self.logger.info(f"Page numbers added successfully to '{output_path}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error adding page numbers to PDF '{pdf_path}': {e}", exc_info=True)
            return False

    def extract_images_from_pdf(self, pdf_path: str, output_dir: str, password: Optional[str] = None) -> bool:
        """
        Extracts all images from a specified PDF file.

        Args:
            pdf_path (str): The file path to the PDF.
            output_dir (str): The directory where extracted images will be saved.
            password (Optional[str], optional): The password for encrypted PDFs. Defaults to None.

        Returns:
            bool: True if images are extracted successfully, False otherwise.
        """
        try:
            self.logger.debug(f"Extracting images from PDF '{pdf_path}' into directory '{output_dir}' with password '{password}'.")
            if not os.path.exists(pdf_path):
                self.logger.error(f"PDF file '{pdf_path}' does not exist.")
                return False
            os.makedirs(output_dir, exist_ok=True)

            reader = PdfReader(pdf_path)
            if reader.is_encrypted:
                if password:
                    reader.decrypt(password)
                else:
                    self.logger.error("PDF is encrypted and no password was provided.")
                    return False

            image_count = 0
            for page_num, page in enumerate(reader.pages, start=1):
                if '/XObject' in page['/Resources']:
                    xObject = page['/Resources']['/XObject'].get_object()
                    for obj in xObject:
                        if xObject[obj]['/Subtype'] == '/Image':
                            size = (xObject[obj]['/Width'], xObject[obj]['/Height'])
                            data = xObject[obj]._data
                            if '/Filter' in xObject[obj]:
                                if xObject[obj]['/Filter'] == '/DCTDecode':
                                    file_type = 'jpg'
                                elif xObject[obj]['/Filter'] == '/FlateDecode':
                                    file_type = 'png'
                                else:
                                    file_type = 'png'
                            else:
                                file_type = 'png'
                            image_path = os.path.join(output_dir, f"page_{page_num}_image_{image_count}.{file_type}")
                            with open(image_path, 'wb') as img_file:
                                img_file.write(data)
                            self.logger.debug(f"Image extracted to '{image_path}'.")
                            image_count += 1
            self.logger.info(f"Extracted {image_count} images from PDF '{pdf_path}' into '{output_dir}'.")
            return True
        except Exception as e:
            self.logger.error(f"Error extracting images from PDF '{pdf_path}': {e}", exc_info=True)
            return False

    def close_service(self):
        """
        Closes any resources or sessions held by the service.
        """
        try:
            self.logger.debug("Closing PDFReaderService resources.")
            # Currently, no persistent resources to close
            self.logger.info("PDFReaderService closed successfully.")
        except Exception as e:
            self.logger.error(f"Error closing PDFReaderService: {e}", exc_info=True)
            raise PDFReaderServiceError(f"Error closing PDFReaderService: {e}")
