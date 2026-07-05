"""
mailgun_service.py
Drop-in Mailgun email service for sending signup invites and other emails
"""

import os
import requests
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# TODO Replace url with production url when ready
domain_address = os.getenv("DOMAIN_ADDRESS")
class MailgunService:
    """Mailgun email service - handles all email operations"""
    
    def __init__(self):
        self.api_key = os.getenv("MAILGUN_API_KEY")
        self.domain = os.getenv("MAILGUN_DOMAIN")
        self.base_url = f"https://api.mailgun.net/v3/{self.domain}"

        # FROM_EMAIL must contain '@' and use the verified/sandbox domain.
        # Fall back to noreply@<MAILGUN_DOMAIN> if not set or malformed.
        configured_from = os.getenv("FROM_EMAIL", "")
        if "@" in configured_from:
            self.from_email = configured_from
        else:
            self.from_email = f"noreply@{self.domain}"
            print(f"⚠️  FROM_EMAIL not set or invalid - using fallback: {self.from_email}")
    
        
        if not self.api_key or not self.domain:
            raise ValueError("MAILGUN_API_KEY and MAILGUN_DOMAIN must be set in .env")
    
    def send_signup_invite(
        self,
        email: str,
        full_name: str,
        invite_link: str,
        plan: str = "demo"
    ) -> Dict[str, Any]:
        """
        Send signup invite/confirmation email
        
        Args:
            email: User's email address
            full_name: User's full name
            invite_link: The invite link to include in email
            plan: Account plan ("demo" or "pro")
        
        Returns:
            Dict with keys: success (bool), message_id (str), error (str)
        """
        print(f"📧 Sending signup invite email to {email}")
        
        subject = f"Welcome to Our App - Confirm Your {plan.upper()} Account!"
        
        html_body = self._get_signup_email_template(full_name, invite_link, plan)
        text_body = f"Welcome {full_name}! Click here to confirm your account: {invite_link}"
        
        return self._send_email(
            to=email,
            subject=subject,
            text=text_body,
            html=html_body
        )

    def send_verification_email(
        self,
        email: str,
        full_name: str,
        verification_link: str
    ) -> Dict[str, Any]:
        """
        Send email verification link
        
        Args:
            email: User's email address
            full_name: User's full name
            verification_link: The verification link to include in email
        
        Returns:
            Dict with keys: success (bool), message_id (str), error (str)
        """
        print(f"📧 Sending email verification to {email}")
        
        subject = "Confirm Your Email Address"
        
        html_body = self._get_verification_email_template(full_name, verification_link)
        text_body = f"Hi {full_name}! Please confirm your email address by clicking here: {verification_link}"
        
        return self._send_email(
            to=email,
            subject=subject,
            text=text_body,
            html=html_body
        )
    
    def send_team_invitation(
        self,
        email: str,
        invite_link: str,
        invited_by_name: str,
        role: str
    ) -> Dict[str, Any]:
        """
        Send team invitation email
        
        Args:
            email: User's email address
            invite_link: The invite link to include in email
            invited_by_name: Name of inviter
            role: Role assigned to user
        
        Returns:
            Dict with keys: success (bool), message_id (str), error (str)
        """
        print(f"📧 Sending team invitation email to {email}")
        
        subject = f"You've been invited to join the team"
        
        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #007bff;">Team Invitation</h2>
                    
                    <p>Hello,</p>
                    
                    <p>You have been invited by <strong>{invited_by_name}</strong> to join the Process Mining platform as a <strong>{role}</strong>.</p>
                    
                    <p>To accept the invitation and set up your account, please click the button below:</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{invite_link}" style="background-color: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                            Join the Team
                        </a>
                    </div>
                    
                    <p>Or copy and paste this link in your browser:</p>
                    <p style="word-break: break-all; background-color: #f5f5f5; padding: 10px; border-radius: 5px;">
                        {invite_link}
                    </p>
                    
                    <p>This invitation expires in 7 days.</p>
                    
                    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                    
                    <p style="font-size: 12px; color: #666;">
                        If you did not expect this invitation, please ignore this email.
                    </p>
                </div>
            </body>
        </html>
        """
        
        text_body = f"You have been invited by {invited_by_name} to join as a {role}. Click here to join: {invite_link}"
        
        return self._send_email(
            to=email,
            subject=subject,
            text=text_body,
            html=html_body
        )
    
    def send_welcome_email(
        self,
        email: str,
        full_name: str,
        plan: str = "demo",
        tenant: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send welcome email after account confirmation
        
        Args:
            email: User's email address
            full_name: User's full name
            plan: Account plan ("demo" or "pro")
            tenant: Tenant name (for pro accounts)
        
        Returns:
            Dict with keys: success (bool), message_id (str), error (str)
        """
        print(f"📧 Sending welcome email to {email}")
        
        subject = "Welcome! Your Account is Ready"
        
        if plan == "pro":
            html_body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                    <h2>Welcome, {full_name}!</h2>
                    <p>Your Pro account has been successfully created.</p>
                    <p><strong>Tenant:</strong> {tenant}</p>
                    <p>You now have access to:</p>
                    <ul>
                        <li>Dedicated tenant resources</li>
                        <li>Advanced features</li>
                        <li>Priority support</li>
                    </ul>
                    <p><a href={domain_address} style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Go to Dashboard</a></p>
                    <p>Questions? Contact support@zanbric.com</p>
                </body>
            </html>
            """
        else:
            html_body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                    <h2>Welcome, {full_name}!</h2>
                    <p>Your Demo account has been successfully created.</p>
                    <p>You now have access to:</p>
                    <ul>
                        <li>Shared demo resources</li>
                        <li>Core features</li>
                        <li>Community support</li>
                    </ul>
                    <p>Ready to upgrade? <a href={domain_address}>Check out our Pro plan</a></p>
                    <p><a href={domain_address} style="background-color: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Go to Dashboard</a></p>
                    <p>Questions? Contact support@zanbric.com</p>
                </body>
            </html>
            """
        
        text_body = f"Welcome {full_name}! Your account is ready. Visit {domain_address}"
        
        return self._send_email(
            to=email,
            subject=subject,
            text=text_body,
            html=html_body
        )
    
    def send_password_reset(
        self,
        email: str,
        full_name: str,
        reset_link: str
    ) -> Dict[str, Any]:
        """
        Send password reset email
        
        Args:
            email: User's email address
            full_name: User's full name
            reset_link: Password reset link
        
        Returns:
            Dict with keys: success (bool), message_id (str), error (str)
        """
        print(f"📧 Sending password reset email to {email}")
        
        subject = "Reset Your Password"
        
        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6;">
                <h2>Password Reset Request</h2>
                <p>Hi {full_name},</p>
                <p>We received a request to reset your password. Click the link below to create a new password.</p>
                <p><a href="{reset_link}" style="background-color: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Reset Password</a></p>
                <p>This link expires in 24 hours.</p>
                <p>If you didn't request this, please ignore this email.</p>
                <p>Support: support@zanbric.com</p>
            </body>
        </html>
        """
        
        text_body = f"Click here to reset your password: {reset_link}\nThis link expires in 24 hours."
        
        return self._send_email(
            to=email,
            subject=subject,
            text=text_body,
            html=html_body
        )
    
    def _send_email(
        self,
        to: str,
        subject: str,
        text: str,
        html: str
    ) -> Dict[str, Any]:
        """
        Internal method to send email via Mailgun API
        
        Returns:
            Dict with keys: success (bool), message_id (str), error (str)
        """
        try:
            response = requests.post(
                f"{self.base_url}/messages",
                auth=("api", self.api_key),
                data={
                    "from": self.from_email,
                    "to": to,
                    "subject": subject,
                    "text": text,
                    "html": html
                }
            )
            
            if response.status_code == 200:
                message_id = response.json().get("id")
                print(f"✅ Email sent successfully. Message ID: {message_id}")
                return {
                    "success": True,
                    "message_id": message_id,
                    "error": None
                }
            else:
                error_msg = response.json().get("message", "Unknown error")
                print(f"❌ Email send failed: {error_msg}")
                return {
                    "success": False,
                    "message_id": None,
                    "error": error_msg
                }
        
        except Exception as e:
            error_msg = f"Exception sending email: {str(e)}"
            print(f"❌ {error_msg}")
            return {
                "success": False,
                "message_id": None,
                "error": error_msg
            }
    
    def _get_signup_email_template(
        self,
        full_name: str,
        invite_link: str,
        plan: str
    ) -> str:
        """Get HTML email template for signup invite"""
        return f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #007bff;">Welcome, {full_name}!</h1>
                    
                    <p>Thank you for signing up for our app with a <strong>{plan.upper()}</strong> plan.</p>
                    
                    <p>Click the button below to confirm your email and complete your account setup:</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{invite_link}" style="background-color: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                            Confirm Your Account
                        </a>
                    </div>
                    
                    <p>Or copy and paste this link in your browser:</p>
                    <p style="word-break: break-all; background-color: #f5f5f5; padding: 10px; border-radius: 5px;">
                        {invite_link}
                    </p>
                    
                    <p>This link expires in 24 hours.</p>
                    
                    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                    
                    <p style="font-size: 12px; color: #666;">
                        If you didn't sign up for this account, please ignore this email.
                    </p>
                    <p style="font-size: 12px; color: #666;">
                        Questions? Contact us at support@yourdomain.com
                    </p>
                </div>
            </body>
        </html>
        """
    
    def _get_verification_email_template(
        self,
        full_name: str,
        verification_link: str
    ) -> str:
        """Get HTML email template for email verification"""
        return f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #28a745;">Verify Your Email</h1>
                    
                    <p>Hi {full_name},</p>
                    
                    <p>Thank you for signing up! Please confirm your email address to activate your account and gain access to the platform.</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{verification_link}" style="background-color: #28a745; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                            Verify Email Address
                        </a>
                    </div>
                    
                    <p>Or copy and paste this link in your browser:</p>
                    <p style="word-break: break-all; background-color: #f5f5f5; padding: 10px; border-radius: 5px;">
                        {verification_link}
                    </p>
                    
                    <p>This verification link will expire in 24 hours.</p>
                    
                    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                    
                    <p style="font-size: 12px; color: #666;">
                        If you did not create an account, no further action is required.
                    </p>
                    <p style="font-size: 12px; color: #666;">
                        Support: support@zanbric.com
                    </p>
                </div>
            </body>
        </html>
        """


# Initialize the service (singleton pattern)
_mailgun_service = None

def get_mailgun_service() -> MailgunService:
    """Get or create Mailgun service instance"""
    global _mailgun_service
    if _mailgun_service is None:
        _mailgun_service = MailgunService()
    return _mailgun_service