import logging
import os
from logging.handlers import RotatingFileHandler

class SLogger:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SLogger, cls).__new__(cls)
            # Tạo logger
            cls._instance.slogger = logging.getLogger("slogger")
            
            # Quan trọng: Xóa tất cả handlers hiện có
            if cls._instance.slogger.handlers:
                for handler in cls._instance.slogger.handlers[:]:
                    cls._instance.slogger.removeHandler(handler)
            
            # Thiết lập propagate = False để ngăn chặn log từ logger này đến root logger
            cls._instance.slogger.propagate = False
            
            cls._instance.slogger.setLevel(logging.DEBUG)
            
            # Tạo formatter chung
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            
            # Thêm console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(formatter)
            cls._instance.slogger.addHandler(console_handler)
            
            # Thêm file handler để lưu log vào file
            log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'mcp-server.log')
            
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=3,
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            cls._instance.slogger.addHandler(file_handler)
        
        return cls._instance
    
    def logger(self):
        return self.slogger
    
    def registerPublisher(self, publisher):
        # Kiểm tra publisher đã tồn tại chưa
        for handler in self.slogger.handlers:
            if handler == publisher:
                return
        self.slogger.addHandler(publisher)


# Tạo instance của logger
SLOG = SLogger().logger()