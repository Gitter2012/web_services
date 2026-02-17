# =============================================================================
# 邮箱验证邮件模板模块
# =============================================================================
# 本模块提供邮箱验证相关邮件的内容模板，包括：
#   1. 验证码邮件 - 用于用户注册前的邮箱验证
#
# 设计决策：
#   - 提供纯文本和HTML两种格式，确保在各种邮件客户端都能正常显示
#   - 使用简洁的设计风格，与 ResearchPulse 品牌一致
#   - 包含安全提示，提醒用户验证码的有效期
# =============================================================================

"""Email templates for verification emails in ResearchPulse."""


def get_verification_email_content(code: str, app_name: str = "ResearchPulse") -> tuple[str, str]:
    """Generate verification email content in both plain text and HTML formats.

    生成验证码邮件的纯文本和HTML内容。

    Args:
        code: 6-digit verification code.
        app_name: Application name for branding.

    Returns:
        tuple[str, str]: (plain_text, html_body)
    """
    plain_text = f"""
{app_name} - 邮箱验证码

您的验证码是：{code}

此验证码将在 5 分钟后失效。

如果这不是您本人的操作，请忽略此邮件。

---
{app_name} 团队
"""

    html_body = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{app_name} - 邮箱验证</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f0f2f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" width="100%" style="max-width: 500px; background-color: #ffffff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                    <!-- Header -->
                    <tr>
                        <td style="padding: 32px 40px 24px; text-align: center; border-bottom: 1px solid #f0f0f0;">
                            <h1 style="margin: 0; font-size: 24px; font-weight: 600; color: #1a1a2e;">
                                {app_name}
                            </h1>
                            <p style="margin: 8px 0 0; font-size: 14px; color: #666;">
                                学术资讯聚合平台
                            </p>
                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td style="padding: 32px 40px;">
                            <h2 style="margin: 0 0 16px; font-size: 18px; font-weight: 600; color: #1a1a2e;">
                                邮箱验证
                            </h2>
                            <p style="margin: 0 0 24px; font-size: 15px; color: #444; line-height: 1.6;">
                                您好！感谢您注册 {app_name}，您的邮箱验证码如下：
                            </p>

                            <!-- Code Box -->
                            <table role="presentation" width="100%">
                                <tr>
                                    <td align="center" style="padding: 24px 0;">
                                        <div style="display: inline-block; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 8px; padding: 16px 40px;">
                                            <span style="font-size: 36px; font-weight: 700; letter-spacing: 8px; color: #ffffff; font-family: 'Courier New', monospace;">
                                                {code}
                                            </span>
                                        </div>
                                    </td>
                                </tr>
                            </table>

                            <!-- Expiry Notice -->
                            <table role="presentation" width="100%" style="margin-top: 24px;">
                                <tr>
                                    <td style="background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 4px;">
                                        <p style="margin: 0; font-size: 13px; color: #92400e;">
                                            ⏰ 此验证码将在 <strong>5 分钟</strong> 后失效，请尽快完成验证。
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 24px 40px 32px; border-top: 1px solid #f0f0f0;">
                            <p style="margin: 0 0 8px; font-size: 13px; color: #888; line-height: 1.5;">
                                如果这不是您本人的操作，请忽略此邮件，您的邮箱不会被绑定。
                            </p>
                            <p style="margin: 0; font-size: 12px; color: #aaa;">
                                — {app_name} 团队
                            </p>
                        </td>
                    </tr>
                </table>

                <!-- Copyright -->
                <p style="margin: 24px 0 0; font-size: 12px; color: #aaa;">
                    此邮件由系统自动发送，请勿直接回复。
                </p>
            </td>
        </tr>
    </table>
</body>
</html>
"""

    return plain_text, html_body


def get_welcome_email_content(username: str, app_name: str = "ResearchPulse") -> tuple[str, str]:
    """Generate welcome email content after successful registration.

    注册成功后发送的欢迎邮件内容。

    Args:
        username: User's username.
        app_name: Application name for branding.

    Returns:
        tuple[str, str]: (plain_text, html_body)
    """
    plain_text = f"""
欢迎加入 {app_name}！

亲爱的 {username}：

恭喜您成功注册 {app_name} 账户！

{app_name} 是一个学术资讯聚合平台，为您提供：
• ArXiv 论文追踪
• RSS 订阅聚合
• 微信公众号精选
• 个性化订阅推送

立即开始探索：设置您的订阅偏好，获取最新学术资讯。

祝您使用愉快！

---
{app_name} 团队
"""

    html_body = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>欢迎加入 {app_name}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f0f2f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" width="100%" style="max-width: 500px; background-color: #ffffff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                    <!-- Header -->
                    <tr>
                        <td style="padding: 32px 40px 24px; text-align: center; border-bottom: 1px solid #f0f0f0;">
                            <h1 style="margin: 0; font-size: 24px; font-weight: 600; color: #1a1a2e;">
                                {app_name}
                            </h1>
                            <p style="margin: 8px 0 0; font-size: 14px; color: #666;">
                                学术资讯聚合平台
                            </p>
                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td style="padding: 32px 40px;">
                            <h2 style="margin: 0 0 16px; font-size: 18px; font-weight: 600; color: #1a1a2e;">
                                欢迎加入，{username}！
                            </h2>
                            <p style="margin: 0 0 24px; font-size: 15px; color: #444; line-height: 1.6;">
                                恭喜您成功注册 {app_name} 账户！我们为您准备了丰富的学术资讯服务。
                            </p>

                            <!-- Features -->
                            <table role="presentation" width="100%" style="margin-bottom: 24px;">
                                <tr>
                                    <td style="padding: 16px; background-color: #f8fafc; border-radius: 8px;">
                                        <p style="margin: 0 0 12px; font-size: 14px; font-weight: 600; color: #1a1a2e;">✨ 平台特色</p>
                                        <ul style="margin: 0; padding-left: 20px; font-size: 14px; color: #555; line-height: 1.8;">
                                            <li>ArXiv 论文追踪</li>
                                            <li>RSS 订阅聚合</li>
                                            <li>微信公众号精选</li>
                                            <li>个性化订阅推送</li>
                                        </ul>
                                    </td>
                                </tr>
                            </table>

                            <!-- CTA Button -->
                            <table role="presentation" width="100%">
                                <tr>
                                    <td align="center">
                                        <a href="#" style="display: inline-block; padding: 14px 32px; background: linear-gradient(135deg, #4ecdc4 0%, #44a3a0 100%); color: #ffffff; text-decoration: none; font-size: 15px; font-weight: 600; border-radius: 8px;">
                                            开始探索
                                        </a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 24px 40px 32px; border-top: 1px solid #f0f0f0;">
                            <p style="margin: 0; font-size: 12px; color: #aaa;">
                                — {app_name} 团队
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

    return plain_text, html_body


def get_password_reset_email_content(code: str, app_name: str = "ResearchPulse") -> tuple[str, str]:
    """Generate password reset email content in both plain text and HTML formats.

    生成密码重置验证码邮件的纯文本和HTML内容。

    Args:
        code: 6-digit verification code.
        app_name: Application name for branding.

    Returns:
        tuple[str, str]: (plain_text, html_body)
    """
    plain_text = f"""
{app_name} - 密码重置验证码

您收到这封邮件是因为您（或其他人）请求重置您的账户密码。

您的验证码是：{code}

此验证码将在 5 分钟后失效。

如果您没有请求重置密码，请忽略此邮件，您的密码不会被更改。

---
{app_name} 团队
"""

    html_body = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{app_name} - 密码重置</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f0f2f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" width="100%" style="max-width: 500px; background-color: #ffffff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                    <!-- Header -->
                    <tr>
                        <td style="padding: 32px 40px 24px; text-align: center; border-bottom: 1px solid #f0f0f0;">
                            <h1 style="margin: 0; font-size: 24px; font-weight: 600; color: #1a1a2e;">
                                {app_name}
                            </h1>
                            <p style="margin: 8px 0 0; font-size: 14px; color: #666;">
                                学术资讯聚合平台
                            </p>
                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td style="padding: 32px 40px;">
                            <h2 style="margin: 0 0 16px; font-size: 18px; font-weight: 600; color: #1a1a2e;">
                                密码重置请求
                            </h2>
                            <p style="margin: 0 0 24px; font-size: 15px; color: #444; line-height: 1.6;">
                                您收到这封邮件是因为有人请求重置您的账户密码。请使用以下验证码完成密码重置：
                            </p>

                            <!-- Code Box -->
                            <table role="presentation" width="100%">
                                <tr>
                                    <td align="center" style="padding: 24px 0;">
                                        <div style="display: inline-block; background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%); border-radius: 8px; padding: 16px 40px;">
                                            <span style="font-size: 36px; font-weight: 700; letter-spacing: 8px; color: #ffffff; font-family: 'Courier New', monospace;">
                                                {code}
                                            </span>
                                        </div>
                                    </td>
                                </tr>
                            </table>

                            <!-- Expiry Notice -->
                            <table role="presentation" width="100%" style="margin-top: 24px;">
                                <tr>
                                    <td style="background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 12px 16px; border-radius: 4px;">
                                        <p style="margin: 0; font-size: 13px; color: #991b1b;">
                                            ⏰ 此验证码将在 <strong>5 分钟</strong> 后失效，请尽快完成密码重置。
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 24px 40px 32px; border-top: 1px solid #f0f0f0;">
                            <p style="margin: 0 0 8px; font-size: 13px; color: #888; line-height: 1.5;">
                                如果您没有请求重置密码，请忽略此邮件，您的密码不会被更改。
                            </p>
                            <p style="margin: 0; font-size: 12px; color: #aaa;">
                                — {app_name} 团队
                            </p>
                        </td>
                    </tr>
                </table>

                <!-- Copyright -->
                <p style="margin: 24px 0 0; font-size: 12px; color: #aaa;">
                    此邮件由系统自动发送，请勿直接回复。
                </p>
            </td>
        </tr>
    </table>
</body>
</html>
"""

    return plain_text, html_body
