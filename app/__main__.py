import uvicorn
import os
from .main import app

if __name__ == '__main__':
    uvicorn.run(app,host='127.0.0.1',port=int(os.getenv('AJOUR_PORT','8765')),log_level='warning')
