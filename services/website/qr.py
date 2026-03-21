import segno
import logging
import io
import base64

logger = logging.getLogger(__name__)
logger.info("Все запишется в один файл")


def generate(self, user_id, event_id):
    temp = segno.make_qr(f"http://assistify.space/validate/{user_id}-{event_id}")
    buffer = io.BytesIO()
    temp.save(buffer, format="png")
    encoded_bytes = base64.b64encode(buffer.getvalue())
    base64_string = encoded_bytes.decode('utf-8')
    logger.info("QR generated")
    return f"data:image/png;base64,{base64_string}"

def validate(self, qr):
    pass
