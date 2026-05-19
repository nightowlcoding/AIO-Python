from flask import Flask, request, jsonify
from downloader import download_image

app = Flask(__name__)

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    image_url = data.get('image_url')
    
    if not image_url:
        return jsonify({'error': 'No image URL provided'}), 400
    
    try:
        file_path = download_image(image_url)
        return jsonify({'message': 'Image downloaded successfully', 'file_path': file_path}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)