# Link-preview metadata (Discord, etc.), read by jekyll-seo-tag in _includes/head.html.
# Fills in, without editing any page:
#   image       -> for guides, assets/img/previews/<file>.jpg (cover + overlay, made by
#                  _tools/make_previews.py); otherwise the page's `cover`, else
#                  `social_image` from _config.yml
#   description -> the first real paragraph of the page (skipping the distribution
#                  notice, tables of contents, tables, lists and headings)
# A page can always set its own `image:` or `description:` in front matter.

module SocialPreview
  MAX = 155

  def self.description_from(markdown)
    text = markdown.gsub(/<(aside|nav|table|figure|details|div)\b.*?<\/\1>/m, "") # callouts, TOCs, tables…
    text.split(/\n\s*\n/).each do |block|
      b = block.strip
      next if b.empty? || b.start_with?("<", "#", "{", "|", "-", "*", "!", ">") || b =~ /\A\d+\./
      b = b.gsub(/\{%.*?%\}|\{\{.*?\}\}/m, " ")      # Liquid
           .gsub(/!\[[^\]]*\]\([^)]*\)/, "")          # images
           .gsub(/\[([^\]]*)\]\([^)]*\)/, '\1')       # links -> text
           .gsub(/<[^>]+>/, " ")                       # HTML tags
           .gsub(/[*_`]+/, "")                         # emphasis / code markers
           .gsub(/\\(.)/, '\1')                        # Markdown escapes
           .gsub(/\s+/, " ").strip
      next if b.length < 40
      return b if b.length <= MAX
      return b[0, MAX].sub(/\s+\S*\z/, "") + "…"
    end
    nil
  end
end

Jekyll::Hooks.register [:pages, :documents], :pre_render do |doc, payload|
  next unless doc.output_ext == ".html"
  data = doc.data
  set = {}
  unless data["image"]
    # Guides: the branded preview made by _tools/make_previews.py, if there is one.
    preview = "/assets/img/previews/#{File.basename(doc.path, ".*")}.jpg"
    is_guide = doc.respond_to?(:collection) && doc.collection && doc.collection.label == "guides"
    set["image"] = if is_guide && File.exist?(File.join(doc.site.source, preview)) then preview
                   else data["cover"] || doc.site.config["social_image"] end
  end
  unless data["description"] || doc.url == "/"   # home page uses the site description
    desc = SocialPreview.description_from(doc.content.to_s)
    set["description"] = desc if desc
  end
  data.merge!(set)
  # Plain pages hand Liquid a copy of their data made before this hook runs.
  payload["page"].merge!(set) if payload && payload["page"].is_a?(Hash)
end
