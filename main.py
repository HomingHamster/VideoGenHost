import json
import os
import mimetypes
import typing
import uuid
from comfy.api import schemas, exceptions
from comfy.api.components.schema.prompt import Prompt
import aiohttp
import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.escape
import random
import json
import copy

from tornado.platform.asyncio import AsyncIOMainLoop

# Dummy user database
USERS = {
    "admin": "password123"
}

PROMPT = {
  "3": {
    "inputs": {
      "seed": 0,
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
      "text": "",
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
      "width": 832,
      "height": 480,
      "length": 33,
      "batch_size": 1
    },
    "class_type": "EmptyHunyuanLatentVideo",
    "_meta": {
      "title": "EmptyHunyuanLatentVideo"
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

class JSONEncoder(json.JSONEncoder):
    compact_separators = (',', ':')

    def default(self, obj: typing.Any):
        if isinstance(obj, str):
            return str(obj)
        elif isinstance(obj, float):
            return obj
        elif isinstance(obj, bool):
            # must be before int check
            return obj
        elif isinstance(obj, int):
            return obj
        elif obj is None:
            return None
        elif isinstance(obj, (dict, schemas.immutabledict)):
            return {key: self.default(val) for key, val in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self.default(item) for item in obj]
        raise exceptions.ApiValueError('Unable to prepare type {} for serialization'.format(obj.__class__.__name__))

# Base handler with common helpers
class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        return self.get_secure_cookie("user")


# Home page – requires login
class MainHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        status = self.get_argument("status", None)
        user = tornado.escape.xhtml_escape(self.current_user.decode())
        video_list_html = self.render_video_list()
        self.render("main.html", user=user, status=status, video_list=video_list_html, xsrf_token=self.xsrf_token)

    def render_video_list(self):
        try:
            videos = os.listdir("videos")
            if not videos:
                return "<p>No videos generated yet</p>"

            items = "\n".join(
                f'<li><a href="/video/{v}">{v}</a></li>'
                for v in videos if v.endswith(".webp")
            )
            return f"<ul>{items}</ul>"
        except FileNotFoundError:
            return "<p>Video directory not found</p>"

    async def post(self):
        client = ComfyUIClient(
            server_address="http://127.0.0.1:8188",
            prompt=self.get_argument("prompt")
        )
        await client.run_workflow_and_save_video()


# Login page
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


# Logout
class LogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie("user")
        self.redirect("/login")


class ComfyUIClient:
    def __init__(self, server_address, prompt):
        self.server_address = server_address
        workflow = copy.deepcopy(PROMPT)
        workflow["6"]["inputs"]["text"] = prompt
        self.prompt = JSONEncoder().encode(Prompt.validate(workflow))
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10 * 60.0, connect=60.0))

    async def run_workflow_and_save_video(self, save_dir="videos"):
        os.makedirs(save_dir, exist_ok=True)
        headers = {'Content-Type': 'application/json'}
        async with self.session.post(self.server_address + "/api/v1/prompts", data=self.prompt,
                                     headers=headers) as response:

            if 200 <= response.status < 400:
                path = os.path.join(save_dir, str(uuid.uuid4()) + ".webp")
                response = await response.read()
                image = await tornado.httpclient.AsyncHTTPClient().fetch(json.loads(response)["urls"][0])
                image = image.body
                with open(path, "wb") as f:
                    f.write(image)
                print(f"Saved video: {path}")
            else:
                raise RuntimeError(f"could not prompt: {response.status}: {await response.text()}")


VIDEO_DIR = "videos"

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

        range_header = self.request.headers.get("Range", None)
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
                chunk = f.read(length)
                self.write(chunk)
        else:
            self.set_header("Content-Length", str(file_size))
            with open(filepath, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    self.write(chunk)

        self.finish()


class PlayerHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("player.html", video_url="/video/sample.mp4")


def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/login", LoginHandler),
        (r"/logout", LogoutHandler),
        (r"/a", PlayerHandler),
        (r"/video/(.*)", VideoStreamHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": "static"}),
    ],
        cookie_secret="__CHANGE_THIS_SECRET__",
        login_url="/login",
        template_path="templates",
        static_path=os.path.join(os.path.dirname(__file__), "static"),
        debug=True
    )


if __name__ == "__main__":
    AsyncIOMainLoop().install()
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
