# FFmpeg for Vercel

Place a Linux executable named `ffmpeg` in this folder:

- `bin/ffmpeg`

The app will try these in order:

1. `FFMPEG_PATH` environment variable
2. `./bin/ffmpeg`
3. `/var/task/bin/ffmpeg`
4. `ffmpeg` from PATH

Requirements:

- File must be executable in Linux runtime.
- Keep binary size as small as possible to reduce deployment bundle size.

Quick local test command:

```bash
./bin/ffmpeg -version
```
