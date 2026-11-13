# Permissions

An app asks only for what its code uses, each with one sentence that says why. Declared is binding: Mixel refuses anything else. The install sheet shows the words below and the app's reason.

| Code | The person reads | Needed for |
| --- | --- | --- |
| `files` | Read and write files you pick | Files and Folder controls; files next to the ones chosen |
| `library` | Add to your Library | returning ox.sound, ox.midi or ox.file; ox.library.add in Python and on the page. It never lists or opens the person's other sounds |
| `library-read` | Read your Library | the page's ox.library.list and ox.library.file, and LibraryDialog: names, length, tempo and key, no paths; a file only for a sound the person picks or the app added |
| `data` | Keep its own files | ox.data in Python and on the page |
| `gpu` | Use the graphics chip | torch or onnxruntime running a model on the graphics chip (Metal on a Mac, CUDA on Linux); without it, the same code runs on the CPU |
| `network` | Use the network | reaching the listed hosts only (downloads, page fetch) |

`network` is `{"why": "…", "hosts": ["example.com"]}`. The whole web, IPs and localhost are refused.
