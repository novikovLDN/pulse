"""File processing for PDF and images."""
import io
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
from typing import Optional
from loguru import logger


class FileProcessor:
    """Process PDF and image files to extract text."""
    
    @staticmethod
    def extract_text_from_pdf(file_bytes: bytes) -> str:
        """Extract text from PDF file."""
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            text_parts = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                
                # If no text found, try OCR
                if not text.strip():
                    pix = page.get_pixmap()
                    img_data = pix.tobytes("png")
                    text = FileProcessor._ocr_image(img_data)
                
                text_parts.append(text)
            
            doc.close()
            return "\n\n".join(text_parts)
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            raise
    
    @staticmethod
    def extract_text_from_image(file_bytes: bytes, image_format: str = "PNG") -> str:
        """Extract text from image using OCR."""
        try:
            return FileProcessor._ocr_image(file_bytes)
        except Exception as e:
            logger.error(f"Error extracting text from image: {e}")
            raise
    
    @staticmethod
    def _ocr_image(image_bytes: bytes) -> str:
        """Perform OCR on image bytes."""
        try:
            image = Image.open(io.BytesIO(image_bytes))
            # Configure Tesseract for Russian and English
            text = pytesseract.image_to_string(
                image,
                lang='rus+eng',
                config='--psm 6'
            )
            return text
        except Exception as e:
            logger.error(f"OCR error: {e}")
            raise
    
    @staticmethod
    def process_file(file_bytes: bytes, file_type: str) -> str:
        """Process file and extract text."""
        if file_type == "pdf" or file_type == "application/pdf":
            return FileProcessor.extract_text_from_pdf(file_bytes)
        elif file_type in ["jpg", "jpeg", "png", "image/jpeg", "image/png"]:
            return FileProcessor.extract_text_from_image(file_bytes)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
