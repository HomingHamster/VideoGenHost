VideoGenHost
============

This repo will allow you to generate short clips using a ComfyUI
instance running locally. It allows you to provide only the prompt,
and get a video file downloaded to the folder this app is running in.
It will also poll for completion, host the video files and provide
a player with buffering.

TODO
----
* Progress reporting beyond pending/completed.
* HTTPS server

Install
-------
1. Follow the ComfyUI install process separately to this app,
and have a running ComfyUI instance.
2. Download this repo and cd into it.
3. Create a venv for this project.

```python -m venv venv```

4. Activate the venv.

```source ./venv/bin/activate```

5. Install the requirements from the requirements file into the venv.

```pip install -r requirements.txt```

6. Run the main.py file and your server will be avialable on http://localhost:8888.

```python main.py```