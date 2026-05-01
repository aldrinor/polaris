# Third-party licenses

## shadcn/ui (MIT)

The components in `components/ui/` are scaffolded by the shadcn CLI from the
upstream registry at <https://ui.shadcn.com>. Per the shadcn project, scaffolded
components are licensed under the MIT License and become part of this repo
(see <https://github.com/shadcn-ui/ui/blob/main/LICENSE.md>).

The shadcn CLI itself (npm package `shadcn` v4.6.0, declared
`"license": "MIT"`) is also MIT-licensed.

Verbatim text of the upstream `LICENSE.md`:

```
MIT License

Copyright (c) 2023 shadcn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Underlying primitives

- `@base-ui/react` (MIT) — Base UI primitive components used by shadcn's
  `base-nova` preset.
- `lucide-react` (ISC) — icon set declared by `components.json`.
- `class-variance-authority` (Apache-2.0), `clsx` (MIT), `tailwind-merge` (MIT),
  `tw-animate-css` (MIT), `sonner` (MIT), `next-themes` (MIT).

License audit produced via `npm install`; see each package's installed
`node_modules/<pkg>/LICENSE`.
