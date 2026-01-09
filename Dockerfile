# SMTP测试工具Docker镜像构建文件
# 基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装依赖
RUN pip install flask flask-cors flask-socketio eventlet gunicorn cryptography==38.0.0

# 复制文件
COPY . /app

# 暴露端口
EXPOSE 5000

# 启动命令
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "eventlet", "-w", "1", "--access-logfile", "-", "--error-logfile", "-", "app:app"]