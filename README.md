# tcd-library
The Transcend Library repository,.

## Link previews (Discord etc.)

`_plugins/social.rb` fills in each page's preview image and description. Guides with a
cover use a branded preview from `assets/img/previews/` (cover + the overlay in
`_tools/assets/preview-overlay.svg`, top right). After changing a cover or the overlay,
regenerate them (needs ImageMagick, `rsvg-convert` and the Apfel Grotezk font installed):

```bash
python3 _tools/make_previews.py
```

Pages without a cover use `assets/img/social-card.png`.
