"""
Email Service Utility
Handles sending invitation emails to users

To enable actual email sending:
1. Install: pip install sendgrid
2. Set SENDGRID_API_KEY in .env
3. Uncomment the SendGrid implementation below
"""

import os
from typing import Optional


def send_invitation_email(
    recipient_email: str,
    invite_url: str,
    invited_by_name: str = "Admin",
    role: str = "VIEWER"
) -> bool:
    """
    Send an invitation email to a new user.
    
    Args:
        recipient_email: Email address of the recipient
        invite_url: Full URL for the invitation signup page
        invited_by_name: Name of the person who sent the invite
        role: Role assigned to the user
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    
    # For now, just log the invitation details
    # In production, integrate with SendGrid, AWS SES, or similar
    print("=" * 80)
    print("📧 INVITATION EMAIL")
    print("=" * 80)
    print(f"To: {recipient_email}")
    print(f"From: {invited_by_name}")
    print(f"Role: {role}")
    print(f"\nInvitation Link: {invite_url}")
    print("\n" + "-" * 80)
    print("Email Body:")
    print("-" * 80)
    print(f"""
Hello,

You have been invited by {invited_by_name} to join our Process Mining platform as a {role}.

To complete your registration, please click the link below:

{invite_url}

This invitation will expire in 7 days.

If you did not expect this invitation, you can safely ignore this email.

Best regards,
Process Mining Team
    """)
    print("=" * 80)
    
    return True


# Uncomment below to use SendGrid for actual email sending
"""
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

def send_invitation_email_sendgrid(
    recipient_email: str,
    invite_url: str,
    invited_by_name: str = "Admin",
    role: str = "VIEWER"
) -> bool:
    '''
    Send invitation email using SendGrid.
    
    Requires:
        - SENDGRID_API_KEY in environment variables
        - SENDGRID_FROM_EMAIL in environment variables
    '''
    try:
        api_key = os.getenv('SENDGRID_API_KEY')
        from_email = os.getenv('SENDGRID_FROM_EMAIL', 'noreply@example.com')
        
        if not api_key:
            print("Warning: SENDGRID_API_KEY not set. Email not sent.")
            return False
        
        message = Mail(
            from_email=from_email,
            to_emails=recipient_email,
            subject=f'You have been invited to join Process Mining Platform',
            html_content=f'''
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #007bff;">Welcome to Process Mining Platform!</h2>
                        
                        <p>Hello,</p>
                        
                        <p>You have been invited by <strong>{invited_by_name}</strong> to join our Process Mining platform as a <strong>{role}</strong>.</p>
                        
                        <p>To complete your registration, please click the button below:</p>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{invite_url}" 
                               style="background-color: #28a745; 
                                      color: white; 
                                      padding: 12px 30px; 
                                      text-decoration: none; 
                                      border-radius: 5px;
                                      display: inline-block;">
                                Complete Registration
                            </a>
                        </div>
                        
                        <p style="color: #666; font-size: 14px;">
                            Or copy and paste this link into your browser:<br>
                            <a href="{invite_url}">{invite_url}</a>
                        </p>
                        
                        <p style="color: #666; font-size: 14px;">
                            <strong>Note:</strong> This invitation will expire in 7 days.
                        </p>
                        
                        <p>If you did not expect this invitation, you can safely ignore this email.</p>
                        
                        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                        
                        <p style="color: #999; font-size: 12px;">
                            Best regards,<br>
                            Process Mining Team
                        </p>
                    </div>
                </body>
            </html>
            '''
        )
        
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        
        if response.status_code in [200, 201, 202]:
            print(f"✅ Invitation email sent to {recipient_email}")
            return True
        else:
            print(f"❌ Failed to send email. Status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error sending email: {str(e)}")
        return False
"""
