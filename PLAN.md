# Project Plan: Badminton Match Automated Uploader

**Objective:** Build a Python CLI tool to batch-process local video files, generate custom thumbnails, and upload them to YouTube reliably.
**Tech Stack:** Python 3.x, OpenCV (Vision), Pillow (Image), Google API Client (YouTube), Python-Dotenv (Config).

---

## I. High-Level Workflow

The automation is split into two stages to ensure user attention is only needed at the start.

### Stage 1: Interactive Prep (User Involved)
* **Trigger:** User runs the script.
* **Loop:** The script iterates through every video in the input folder.
    1.  **Auto-Analysis:** Parses filename for metadata and extracts 5 "sharp" frames.
    2.  **Human Review:** Opens the temporary candidate folder. The user selects the best image ID (1-5) via CLI.
    3.  **Processing:** Script immediately polishes the chosen image (color/text) and saves it to a "ready" folder.
* **Outcome:** A queue of approved videos and thumbnails, ready for upload.

### Stage 2: Autonomous Upload (Bot Only)
* **Trigger:** User confirms "Start Upload" after Stage 1 is complete.
* **Loop:** The script iterates through the queue.
    1.  **Upload:** Pushes the video and its corresponding thumbnail to YouTube.
    2.  **Cleanup:** Moves the source video to the completed folder.
* **Outcome:** All videos are live on YouTube; local folders are clean.

---

## II. Development Phases

We will build this iteratively to ensure each part works before moving to the next.

### Phase 1: Environment & Configuration
Goal: Establish the project structure and ensure the script can see your files.

* 1.1. Project Skeleton: Create the root directory and sub-folders (`_processing_zone`, `_processing_zone/ready_thumbnails`).
* 1.2. Configuration Manager: Implement `python-dotenv` and a `.env` file to store input/output paths and API secrets.
* 1.3. File Scanner: Write a function to scan the input directory for `.mp4` files.

### Phase 2: The Metadata Engine
Goal: Turn filenames into structured data (Titles, Descriptions, Tags).

* 2.1. Naming Convention Parser: Implement logic to split filenames (e.g., input `YonexOpen - Axelsen vs Momota - Final.mp4`).
* 2.2. Text Generator: Create templates for the YouTube Title and Description using the parsed data.
* 2.3. Fallback Mechanism: If parsing fails, prompt the user to manually enter details.

### Phase 3: The Vision Module (Thumbnail Prep)
Goal: Extract high-quality images from video files without manual seeking.

* 3.1. Interval Sampler: Use OpenCV to jump to 5 distinct points in the video (e.g., 15%, 30%, 45%...).
* 3.2. Blur Detection: Implement the Laplacian Variance algorithm to score frame sharpness.
* 3.3. Candidate Generator: Extract the sharpest frame from each interval and save to a temporary folder.
* 3.4. Auto-Opener: Automatically open the folder window for user review.

### Phase 4: The Image Processor (Thumbnail Polish)
Goal: Turn a raw frame into a clickable thumbnail.

* 4.1. Color Grading: Use Pillow or OpenCV to boost saturation and contrast.
* 4.2. Text Overlay: Programmatically draw the players' names and round info onto the image.
* 4.3. Pipeline Integration: Connect Phase 3 and 4 so selecting an ID immediately triggers processing.

### Phase 5: The Uploader (YouTube API)
Goal: Reliable, resumable uploading.

* 5.1. Authentication: Set up OAuth 2.0 for YouTube channel access.
* 5.2. Video Uploader: Implement the API's `insert` method for resumable uploads.
* 5.3. Thumbnail Uploader: Implement the API's `thumbnails().set` method.
* 5.4. File Mover: Move uploaded videos to the archive folder upon success.
