# services/__init__.py

"""
Initialization of the services package.
"""

from .social_media_service import SocialMediaService
from .email_service import EmailService
from .web_browsing_service import WebBrowsingService

__all__ = [
    'SocialMediaService',
    'EmailService',
    'WebBrowsingService',
]
