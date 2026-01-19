"""Templates for web selector."""

SELECT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Select Thumbnail</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #1a1a1a;
            color: #fff;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
            min-height: 100vh;
        }
        
        .container {
            max-width: 1200px;
            width: 100%;
        }
        
        h1 {
            text-align: center;
            margin-bottom: 30px;
            color: #fff;
        }
        
        .preview-container {
            display: flex;
            justify-content: center;
            margin-bottom: 30px;
        }
        
        #previewCanvas {
            max-width: 100%;
            height: auto;
            border: 2px solid #444;
            border-radius: 8px;
            background: #000;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
        }
        
        .controls {
            display: flex;
            flex-direction: column;
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .timeline-container {
            width: 100%;
        }
        
        .timeline-label {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 14px;
            color: #aaa;
        }
        
        #timelineSlider {
            width: 100%;
            height: 8px;
            border-radius: 4px;
            background: #333;
            outline: none;
            -webkit-appearance: none;
            appearance: none;
        }
        
        #timelineSlider::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: #4CAF50;
            cursor: pointer;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
        }
        
        #timelineSlider::-moz-range-thumb {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: #4CAF50;
            cursor: pointer;
            border: none;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
        }
        
        .info {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px;
            background: #2a2a2a;
            border-radius: 8px;
            font-size: 14px;
        }
        
        .select-button {
            width: 100%;
            padding: 15px 30px;
            font-size: 18px;
            font-weight: bold;
            color: #fff;
            background: #4CAF50;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: background 0.3s;
        }
        
        .select-button:hover {
            background: #45a049;
        }
        
        .select-button:active {
            background: #3d8b40;
        }
        
        .select-button:disabled {
            background: #666;
            cursor: not-allowed;
        }
        
        .loading {
            display: none;
            text-align: center;
            color: #4CAF50;
            margin-top: 10px;
        }
        
        #videoElement {
            display: none;
        }
        
        .error {
            color: #f44336;
            text-align: center;
            margin-top: 10px;
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Select Thumbnail Frame</h1>
        
        <div class="preview-container">
            <canvas id="previewCanvas" width="1280" height="720"></canvas>
        </div>
        
        <div class="controls">
            <div class="timeline-container">
                <div class="timeline-label">
                    <span>0:00</span>
                    <span id="currentTime">0:00</span>
                    <span id="totalTime">0:00</span>
                </div>
                <input type="range" id="timelineSlider" min="0" max="100" value="0" step="0.01">
            </div>
            
            <div class="info">
                <span>Drag the slider to navigate through the video</span>
            </div>
            
            <button id="selectButton" class="select-button">Select This Frame</button>
            <div id="loading" class="loading">Saving selection...</div>
            <div id="error" class="error"></div>
        </div>
    </div>
    
    <video id="videoElement" preload="metadata"></video>
    
    <script>
        const video = document.getElementById('videoElement');
        const canvas = document.getElementById('previewCanvas');
        const ctx = canvas.getContext('2d');
        const slider = document.getElementById('timelineSlider');
        const selectButton = document.getElementById('selectButton');
        const currentTimeSpan = document.getElementById('currentTime');
        const totalTimeSpan = document.getElementById('totalTime');
        const loadingDiv = document.getElementById('loading');
        const errorDiv = document.getElementById('error');
        
        let videoDuration = 0;
        let isDragging = false;
        let updateThrottle = null;
        
        function formatTime(seconds) {
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${mins}:${secs.toString().padStart(2, '0')}`;
        }
        
        function updateFrame() {
            if (video.readyState >= 2) {
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            }
        }
        
        function updatePreview() {
            if (updateThrottle) {
                clearTimeout(updateThrottle);
            }
            
            updateThrottle = setTimeout(() => {
                updateFrame();
            }, 50);
        }
        
        function updateSliderFromVideo() {
            if (!isDragging && videoDuration > 0) {
                const percent = (video.currentTime / videoDuration) * 100;
                slider.value = percent;
                currentTimeSpan.textContent = formatTime(video.currentTime);
            }
        }
        
        function handleSliderChange() {
            if (videoDuration > 0) {
                const percent = parseFloat(slider.value);
                video.currentTime = (percent / 100) * videoDuration;
                currentTimeSpan.textContent = formatTime(video.currentTime);
                updatePreview();
            }
        }
        
        slider.addEventListener('input', () => {
            isDragging = true;
            handleSliderChange();
        });
        
        slider.addEventListener('mousemove', (e) => {
            if (e.buttons === 1) {
                isDragging = true;
                handleSliderChange();
            }
        });
        
        slider.addEventListener('mousedown', () => {
            isDragging = true;
        });
        
        slider.addEventListener('mouseup', () => {
            isDragging = false;
        });
        
        slider.addEventListener('touchmove', () => {
            isDragging = true;
            handleSliderChange();
        });
        
        slider.addEventListener('touchend', () => {
            isDragging = false;
        });
        
        video.addEventListener('loadedmetadata', () => {
            videoDuration = video.duration;
            slider.max = 100;
            totalTimeSpan.textContent = formatTime(videoDuration);
            updateFrame();
        });
        
        video.addEventListener('timeupdate', updateSliderFromVideo);
        
        video.addEventListener('seeked', () => {
            updateFrame();
        });
        
        selectButton.addEventListener('click', async () => {
            selectButton.disabled = true;
            loadingDiv.style.display = 'block';
            errorDiv.style.display = 'none';
            
            try {
                const imageData = canvas.toDataURL('image/jpeg', 0.9);
                
                const response = await fetch('/select', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ image: imageData }),
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || 'Failed to save selection');
                }
                
                loadingDiv.textContent = 'Selection saved! Closing...';
                setTimeout(() => {
                    window.close();
                }, 1000);
            } catch (error) {
                errorDiv.textContent = error.message;
                errorDiv.style.display = 'block';
                selectButton.disabled = false;
                loadingDiv.style.display = 'none';
            }
        });
        
        video.src = '/video';
        video.load();
    </script>
</body>
</html>
"""
