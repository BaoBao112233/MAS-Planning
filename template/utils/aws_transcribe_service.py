import os
import logging
import boto3
from template.configs.environments import env

# Cấu hình logging
logger = logging.getLogger(__name__)


class AWSTranscribeService:
    """Service upload audio lên S3"""
    
    def __init__(self):
        """
        Khởi tạo AWS S3 Service
        
        Upload file audio lên S3 và trả về URL public
        """
        self.s3_bucket_name = env.AWS_S3_BUCKET
        self.s3_bucket_key = "audio_evaluation"
        self.aws_region = env.AWS_S3_REGION or "ap-southeast-1"
        
        # Kiểm tra các biến môi trường bắt buộc
        if not self.s3_bucket_name:
            raise ValueError("Biến môi trường AWS_S3_BUCKET không được thiết lập")
        
        aws_access_key = env.AWS_ACCESS_KEY_ID
        aws_secret_key = env.AWS_ACCESS_KEY_SECRET
        
        if not aws_access_key or not aws_secret_key:
            raise ValueError("Biến môi trường AWS_ACCESS_KEY_ID và AWS_SECRET_ACCESS_KEY phải được thiết lập")
        
        # Khởi tạo S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=self.aws_region
        )
        
        logger.info(f"Đã khởi tạo AWSTranscribeService với bucket: {self.s3_bucket_name}")

    def upload_to_s3(self, local_file_path: str, s3_key: str = None) -> str:
        """
        Upload file lên S3 và trả về URL public
        
        Args:
            local_file_path: Đường dẫn file local cần upload
            s3_key: Key trên S3 (nếu None sẽ dùng tên file)
            
        Returns:
            URL public của file trên S3 (có thể play trực tiếp trên browser)
        """
        try:
            # Nếu không có s3_key thì tự động tạo từ tên file
            if s3_key is None:
                object_name = os.path.basename(local_file_path)
                s3_key = f"{self.s3_bucket_key}/{object_name}"
            
            # Xác định Content-Type dựa trên phần mở rộng file
            file_extension = os.path.splitext(local_file_path)[1].lower()
            content_type_map = {
                '.mp3': 'audio/mpeg',
                '.wav': 'audio/wav',  # Sử dụng audio/wav - được hỗ trợ rộng rãi nhất
                '.ogg': 'audio/ogg',
                '.webm': 'audio/webm',
                '.m4a': 'audio/mp4',
                '.flac': 'audio/flac'
            }
            content_type = content_type_map.get(file_extension, 'audio/mpeg')
            
            # Upload file lên S3 với metadata để play trực tiếp trên browser
            self.s3_client.upload_file(
                local_file_path, 
                self.s3_bucket_name, 
                s3_key,
                ExtraArgs={
                    'ACL': 'public-read',
                    'ContentType': content_type,
                    'ContentDisposition': 'inline'  # inline = play on browser, attachment = download
                }
            )
            
            # Tạo URL public
            public_url = f"https://{self.s3_bucket_name}.s3.{self.aws_region}.amazonaws.com/{s3_key}"
            
            logger.info(f"Đã upload file {local_file_path} lên S3")
            logger.info(f"Content-Type: {content_type}")
            logger.info(f"URL: {public_url}")
            
            return public_url
            
        except Exception as e:
            logger.error(f"Lỗi khi upload file lên S3: {e}")
            raise


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    service = AWSTranscribeService()
    
    # Test upload
    audio_file = "audio_data/downloaded_audio.wav"
    if os.path.exists(audio_file):
        url = service.upload_to_s3(audio_file)
        print(f"Audio URL: {url}")
    else:
        print(f"File {audio_file} không tồn tại")