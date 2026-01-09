"""
SMTP测试工具后端服务
主要功能：
1. 提供SMTP邮件发送API
2. 实时Socket.IO日志推送
3. 前端配置管理API
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
import smtplib
from email.mime.text import MIMEText
import os
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

# 创建Flask应用
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# 静态文件路由
@app.route('/')
def index():
    return send_from_directory('.', 'frontend_smtp_tester.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

# SMTP邮件发送API
@app.route('/api/sendmail', methods=['POST'])
def send_mail():
    try:
        data = request.get_json()
        if not data:
            raise ValueError("无效的请求数据")
        
        msg = MIMEText(data.get('body', ''))
        msg['Subject'] = data.get('subject', 'SMTP测试邮件')
        msg['From'] = data.get('sender', '')
        msg['To'] = data.get('recipient', '')
        
        host = data.get('host', '')
        port = int(data.get('port', 587))
        username = data.get('username', '')
        password = data.get('password', '')  # 正确定义password变量
        
        # 智能解密函数（支持可选加密）
        def smart_decrypt(encrypted_data):
            if not encrypted_data:
                return ""
            if encrypted_data.startswith('ENCRYPTED:'):
                encrypted = encrypted_data.replace('ENCRYPTED:', '')
                decrypted = private_key.decrypt(
                    base64.b64decode(encrypted),
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None
                    )
                )
                return decrypted.decode('utf-8')
            return encrypted_data  # 非加密字段原样返回

        # 强制密码加密
        if not data.get('password', '').startswith('ENCRYPTED:'):
            return jsonify({'error': '密码必须使用RSA加密传输'}), 400

        # 解密所有字段（密码必须加密，其他字段可选）
        try:
            password = smart_decrypt(data.get('password', ''))
            username = smart_decrypt(data.get('username', ''))
            sender = smart_decrypt(data.get('sender', ''))
            recipient = smart_decrypt(data.get('recipient', ''))
            subject = smart_decrypt(data.get('subject', ''))
            body = smart_decrypt(data.get('body', ''))
        except Exception as e:
            socketio.emit('log', {'message': f"❌ 密码解密失败: {str(e)}", 'type': 'error'})
            return jsonify({'error': '密码解密失败'}), 400
            try:
                encrypted = password.replace('ENCRYPTED:', '')
                password_bytes = private_key.decrypt(
                    base64.b64decode(encrypted),
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None
                    )
                )
                password = password_bytes.decode('utf-8')
            except Exception as e:
                socketio.emit('log', {'message': f"❌ 密码解密失败: {str(e)}", 'type': 'error'})
                raise ValueError("密码解密失败")
        method = data.get('method', 'starttls')  # 获取用户选择的协议

        socketio.emit('log', {'message': f"🚀 正在连接 {host}:{port} ({method})", 'type': 'info'})
        
        # 根据用户选择的协议进行测试
        if method == 'ssl':
            socketio.emit('log', {'message': f"🔒 使用SSL加密连接端口{port}...", 'type': 'info'})
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                server.set_debuglevel(1)
                socketio.emit('log', {'message': "🔑 正在登录...", 'type': 'info'})
                server.login(username, password)
                server.send_message(msg)
                
        elif method == 'starttls':
            socketio.emit('log', {'message': f"🔐 使用STARTTLS加密连接端口{port}...", 'type': 'info'})
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls()
                server.set_debuglevel(1)
                server.login(username, password)
                server.send_message(msg)
                
        elif method == 'plain':
            socketio.emit('log', {'message': f"⚠️ 使用明文连接端口{port}...", 'type': 'warning'})
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.set_debuglevel(1)
                server.login(username, password)
                server.send_message(msg)
                
        else:
            raise ValueError(f"不支持的协议类型: {method}")
        
        socketio.emit('log', {'message': "✅ 邮件发送成功", 'type': 'success'})
        return jsonify({'status': 'success'})
    
    except Exception as e:
        error_msg = str(e)
        
        # 常见错误信息本地化
        if "No address found" in error_msg:
            error_msg = "无法解析服务器地址，请检查域名或IP是否正确"
        elif "ECONNREFUSED" in error_msg:
            error_msg = "连接被拒绝，目标服务器可能未开启该端口服务"
        elif "password error" in error_msg or "4.7.0" in error_msg:
            error_msg = "认证失败：用户名或密码错误"
        elif "timed out" in error_msg:
            error_msg = "连接超时，请检查网络或防火墙设置"
        elif "RCPT arg" in error_msg or "5.5.2" in error_msg:
            error_msg = "收件人邮箱格式不正确，请输入有效的邮箱地址"
        elif "SMTP AUTH extension not supported" in error_msg:
            error_msg = "服务器不支持SMTP认证，请检查服务器配置"
        elif "WRONG_VERSION_NUMBER" in error_msg:
            error_msg = "SSL协议版本不兼容：请检查服务器支持的TLS版本"
        elif "SSL:" in error_msg:
            if "CERTIFICATE_VERIFY_FAILED" in error_msg:
                error_msg = "证书验证失败：无法确认服务器身份"
            elif "UNSUPPORTED_PROTOCOL" in error_msg:
                error_msg = "不支持的SSL协议：服务器可能已禁用老旧协议"
            else:
                error_msg = "SSL连接失败：请检查加密配置"
        elif "Connection unexpectedly closed" in error_msg:
            if 'method' in locals() and method == 'starttls':
                error_msg = "连接被意外关闭：该端口可能仅支持SSL加密或不支持STARTTLS"
            else:
                error_msg = "连接被意外关闭：请检查端口服务是否正常运行"
        elif "NO_SHARED_CIPHER" in error_msg:
            error_msg = "加密算法不兼容：服务器要求更强的加密套件"
        elif "5.7.1 Relaying denied" in error_msg:
            error_msg = "中继拒绝：该服务器不允许通过当前身份发送邮件"
        elif "send HELO first" in error_msg:
            error_msg = "协议流程错误：未完成EHLO/HELO握手"
        # SMTP状态码错误
        elif "421 4.4.2" in error_msg:
            error_msg = "服务器繁忙或网络不稳定，请稍后重试"
        elif "450 4.7.1" in error_msg:
            error_msg = "发送频率过高，请等待一段时间后重试"
        elif "451 4.7.1" in error_msg:
            error_msg = "服务器临时故障，请稍后重试"
        elif "452 4.5.3" in error_msg:
            error_msg = "服务器邮箱已满，无法接收邮件"
        # 认证扩展错误
        elif "535 5.7.8" in error_msg:
            error_msg = "认证失败：用户名或密码不正确"
        elif "534 5.7.14" in error_msg:
            error_msg = "需要应用专用密码，请使用授权码登录"
        # 网络中间件错误
        elif "Connection aborted" in error_msg:
            error_msg = "网络连接被中间设备中断"
        elif "Broken pipe" in error_msg:
            error_msg = "网络连接异常中断"
        # DNS错误
        elif "Temporary failure in name resolution" in error_msg:
            error_msg = "DNS解析临时故障，请检查网络设置"
        elif "Name or service not known" in error_msg:
            error_msg = "域名不存在或DNS配置错误"
        # 邮件内容错误
        elif "Message too large" in error_msg:
            error_msg = "邮件大小超过服务器限制"
        elif "Invalid header" in error_msg:
            error_msg = "邮件头格式无效"
        else:
            error_msg = f"错误: {error_msg}"
        
        socketio.emit('log', {'message': f"❌ 发送失败: {error_msg}", 'type': 'error'})
        return jsonify({'status': 'error', 'message': error_msg}), 500

# 生成RSA密钥对
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)
public_pem = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
).decode('utf-8')

# 返回空favicon响应（消除404日志污染）
@app.route('/favicon.ico')
def favicon():
    return '', 204  # HTTP 204 = No Content

@app.route('/api/config')
def get_config():
    # 强制重新加载环境变量
    from flask import current_app
    current_app.config.update({
        'COPYRIGHT_YEAR': os.environ.get('COPYRIGHT_YEAR', '2026'),
        'COPYRIGHT_TEXT': os.environ.get('COPYRIGHT_TEXT', 'SMTP测试工具'),
        'COPYRIGHT_LINK': os.environ.get('COPYRIGHT_LINK', ''),
        'PAGE_TITLE': os.environ.get('PAGE_TITLE', 'SMTP全面测试工具'),
        'PAGE_SUBTITLE': os.environ.get('PAGE_SUBTITLE', '实时测试工具 - 动态显示测试过程'),
        'FAVICON_URL': os.environ.get('FAVICON_URL', '')
    })
    
    return jsonify({
        'public_key': public_pem,
        'copyright': {
            'year': current_app.config['COPYRIGHT_YEAR'],
            'text': current_app.config['COPYRIGHT_TEXT'],
            'link': current_app.config['COPYRIGHT_LINK']
        },
        'page': {
            'title': current_app.config['PAGE_TITLE'],
            'subtitle': current_app.config['PAGE_SUBTITLE']
        },
        'favicon_url': current_app.config['FAVICON_URL']
    })

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)