import json
import os
import mimetypes
import random
import typing
import uuid
import copy
from collections import defaultdict
import tornado.ioloop
import tornado.web
import tornado.escape
import tornado.httpclient
from comfy.api import schemas, exceptions
from comfy.api.components.schema.prompt import Prompt

#mock user db
USERS = {
    "admin": "password123"
}


VIDEO_DIR = "videos"


#define a test that check the dict is saved correctly (probably unnecessary)
TASKS = defaultdict(lambda: {"status": "pending", "filename": None})


#the comfyui workflow as a python dict (exported from comfyui using the
#API workflow export feature, which is enabled in settings)
PROMPT = {
  "3": {
    "inputs": {
      "seed": random.randint(0, 2**32 - 1),
      "steps": 30,
      "cfg": 6,
      "sampler_name": "uni_pc",
      "scheduler": "simple",
      "denoise": 1,
      "model": [
        "48",
        0
      ],
      "positive": [
        "6",
        0
      ],
      "negative": [
        "7",
        0
      ],
      "latent_image": [
        "40",
        0
      ]
    },
    "class_type": "KSampler",
    "_meta": {
      "title": "KSampler"
    }
  },
  "6": {
    "inputs": {
      "text": "A video file to be played on a billboard. Attention grabbing. \"In 2023 David Sinclair reversed the age of a monkey...\" Fades to \"Isn't it time we thought about how this is going to work\" Fades to \"https:",
      "clip": [
        "38",
        0
      ]
    },
    "class_type": "CLIPTextEncode",
    "_meta": {
      "title": "CLIP Text Encode (Positive Prompt)"
    }
  },
  "7": {
    "inputs": {
      "text": "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走",
      "clip": [
        "38",
        0
      ]
    },
    "class_type": "CLIPTextEncode",
    "_meta": {
      "title": "CLIP Text Encode (Negative Prompt)"
    }
  },
  "8": {
    "inputs": {
      "samples": [
        "3",
        0
      ],
      "vae": [
        "39",
        0
      ]
    },
    "class_type": "VAEDecode",
    "_meta": {
      "title": "VAE Decode"
    }
  },
  "28": {
    "output_dir": "/home/ubuntu/PycharmProjects/VideoGenHost/videos",
    "inputs": {
      "filename_prefix": "ComfyUI",
      "fps": 16,
      "lossless": False,
      "quality": 90,
      "method": "default",
      "images": [
        "8",
        0
      ]
    },
    "class_type": "SaveAnimatedWEBP",
    "_meta": {
      "title": "SaveAnimatedWEBP"
    }
  },
  "37": {
    "inputs": {
      "unet_name": "wan2.1_t2v_1.3B_fp16.safetensors",
      "weight_dtype": "default"
    },
    "class_type": "UNETLoader",
    "_meta": {
      "title": "Load Diffusion Model"
    }
  },
  "38": {
    "inputs": {
      "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
      "type": "wan",
      "device": "default"
    },
    "class_type": "CLIPLoader",
    "_meta": {
      "title": "Load CLIP"
    }
  },
  "39": {
    "inputs": {
      "vae_name": "wan_2.1_vae.safetensors"
    },
    "class_type": "VAELoader",
    "_meta": {
      "title": "Load VAE"
    }
  },
  "40": {
    "inputs": {
      "width": 624,
      "height": 320,
      "length": 53,
      "batch_size": 1
    },
    "class_type": "EmptyHunyuanLatentVideo",
    "_meta": {
      "title": "EmptyHunyuanLatentVideo"
    }
  },
  "47": {
    "inputs": {
      "filename_prefix": "ComfyUI",
      "codec": "vp9",
      "fps": 24,
      "crf": 32,
      "images": [
        "8",
        0
      ]
    },
    "class_type": "SaveWEBM",
    "_meta": {
      "title": "SaveWEBM"
    }
  },
  "48": {
    "inputs": {
      "shift": 8,
      "model": [
        "37",
        0
      ]
    },
    "class_type": "ModelSamplingSD3",
    "_meta": {
      "title": "ModelSamplingSD3"
    }
  }
}


#sublass the JSONEncoder class from the default json library to cope with the comfyui schema
class JSONEncoder(json.JSONEncoder):
    def default(self, obj: typing.Any):
        if isinstance(obj, str): return str(obj)
        elif isinstance(obj, float): return obj
        elif isinstance(obj, bool): return obj
        elif isinstance(obj, int): return obj
        elif obj is None: return None
        elif isinstance(obj, (dict, schemas.immutabledict)):
            return {key: self.default(val) for key, val in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self.default(item) for item in obj]
        raise exceptions.ApiValueError('Unable to prepare type {} for serialization'.format(obj.__class__.__name__))


#define a base view for tornado that appends the current user to the class so we can use the username from the cookie
class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        return self.get_secure_cookie("user")


#define the homepage view that renders the main template while the user is logged in and forwards to the default
#login page if not
class MainHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        user = tornado.escape.xhtml_escape(self.current_user.decode())
        video_list_html = self.render_video_list()
        self.render("main.html", user=user, video_list=video_list_html, xsrf_token=self.xsrf_token)

    @tornado.web.authenticated
    def render_video_list(self):
        try:
            videos = os.listdir(VIDEO_DIR)
            items = "\n".join(
                f'<li><a href="/player/{v}">{v}</a></li>'
                for v in videos if v.endswith(".webp")
            )
            return f"<ul>{items}</ul>" if items else "<p>No videos generated yet</p>"
        except FileNotFoundError:
            return "<p>Video directory not found</p>"


#define the login page handler/view
class LoginHandler(BaseHandler):
    def get(self):
        self.write("""
            <form action="/login" method="post">
                Username: <input name="username" type="text"/><br/>
                Password: <input name="password" type="password"/><br/>
                <input type="submit" value="Login"/>
            </form>
        """)

    def post(self):
        username = self.get_argument("username")
        password = self.get_argument("password")
        if USERS.get(username) == password:
            self.set_secure_cookie("user", username)
            self.redirect("/")
        else:
            self.write("Login failed. <a href='/login'>Try again</a>")


#define a logout page handler/view that removes the cookie
class LogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie("user")
        self.redirect("/login")


#define a view that catalogs the task and also sends it to comfy ui
class StartGenerationHandler(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        prompt = self.get_argument("prompt")
        task_id = str(uuid.uuid4())
        TASKS[task_id] = {"status": "pending", "filename": None}

        client = ComfyUIClient("http://127.0.0.1:8188", prompt)
        tornado.ioloop.IOLoop.current().spawn_callback(client.run_workflow_and_save_video, task_id)

        self.write({"task_id": task_id})


#define a view that is polled to keep track of when the task is complete
class StatusHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, task_id):
        task = TASKS.get(task_id)
        if not task:
            self.set_status(404)
            return self.write({"status": "not_found"})
        self.write(task)


#define a view that sends the video file itself in a way that can be buffered by the player
class VideoStreamHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Accept-Ranges", "bytes")

    async def get(self, filename):
        filepath = os.path.join(VIDEO_DIR, filename)
        if not os.path.exists(filepath):
            raise tornado.web.HTTPError(404, f"{filename} not found")

        file_size = os.path.getsize(filepath)
        content_type, _ = mimetypes.guess_type(filepath)
        self.set_header("Content-Type", content_type or "application/octet-stream")

        range_header = self.request.headers.get("Range")
        if range_header:
            bytes_range = range_header.replace("bytes=", "").split("-")
            start = int(bytes_range[0])
            end = int(bytes_range[1]) if bytes_range[1] else file_size - 1
            length = end - start + 1
            self.set_status(206)
            self.set_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.set_header("Content-Length", str(length))
            with open(filepath, "rb") as f:
                f.seek(start)
                self.write(f.read(length))
        else:
            self.set_header("Content-Length", str(file_size))
            with open(filepath, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    self.write(chunk)
        self.finish()


#a view that renders the js player
class PlayerHandler(tornado.web.RequestHandler):
    def get(self, filename):
        self.render("player.html", video_url=f"/video/{filename}")


#a class (not a tornado view) that implients the tasks used by the status and start views
#this class controlls comfy ui via the api
class ComfyUIClient:
    def __init__(self, server_address, prompt):
        self.server_address = server_address
        workflow = copy.deepcopy(PROMPT)
        workflow["6"]["inputs"]["text"] = prompt
        self.prompt = JSONEncoder().encode(Prompt.validate(workflow))

    async def run_workflow_and_save_video(self, task_id, save_dir="videos"):
        os.makedirs(save_dir, exist_ok=True)
        headers = {'Content-Type': 'application/json'}
        http_client = tornado.httpclient.AsyncHTTPClient()

        try:
            response = await http_client.fetch(
                self.server_address + "/api/v1/prompts",
                method="POST",
                headers=headers,
                body=self.prompt,
                request_timeout=600
            )
            data = json.loads(response.body.decode())
            video_url = data["urls"][0]
        except Exception as e:
            TASKS[task_id] = {"status": "error", "filename": None}
            return

        try:
            video_response = await http_client.fetch(video_url)
            path = os.path.join(save_dir, str(uuid.uuid4()) + ".webp")
            with open(path, "wb") as f:
                f.write(video_response.body)
            TASKS[task_id] = {"status": "complete", "filename": os.path.basename(path)}
        except Exception as e:
            TASKS[task_id] = {"status": "error", "filename": None}


#set up the url linkings for tornado to link the views to the urls and set the settings we need
#it also tells tornado to host any static files (unused), the videos are returned to the player
#by the VideoStreamHandler not the static file handler.
def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/login", LoginHandler),
        (r"/logout", LogoutHandler),
        (r"/start", StartGenerationHandler),
        (r"/status/(.*)", StatusHandler),
        (r"/video/(.*)", VideoStreamHandler),
        (r"/player/(.*)", PlayerHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": "static"}),
    ],
        cookie_secret="__CHANGE_THIS_SECRET__",
        login_url="/login",
        template_path="templates",
        static_path=os.path.join(os.path.dirname(__file__), "static"),
        debug=False
    )


#run the app and listen on port 8888
if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
