#include <gtk/gtk.h>
int capture(GtkWidget *widget, const char *path) {
  GtkWidget *background = widget;
  if (GTK_IS_WINDOW(widget)) widget = gtk_window_get_child(GTK_WINDOW(widget));
  else if (GTK_IS_POPOVER(widget)) widget = gtk_widget_get_first_child(widget);
  int width = gtk_widget_get_width(widget), height = gtk_widget_get_height(widget);
  if (width <= 0 || height <= 0) return 1;
  width += gtk_widget_get_margin_start(widget) + gtk_widget_get_margin_end(widget);
  height += gtk_widget_get_margin_top(widget) + gtk_widget_get_margin_bottom(widget);
  int requested_width = -1, requested_height = -1;
  gtk_widget_get_size_request(background, &requested_width, &requested_height);
  if (requested_width > 0) width = requested_width;
  if (requested_height > 0) height = requested_height;
  gtk_widget_allocate(widget, width, height, -1, NULL);
  GtkSnapshot *snapshot = gtk_snapshot_new();
  gtk_snapshot_render_background(snapshot, gtk_widget_get_style_context(background), 0, 0, width, height);
  GtkWidget *parent = gtk_widget_get_parent(widget);
  if (parent) gtk_widget_snapshot_child(parent, widget, snapshot);
  else {
    GdkPaintable *paintable = gtk_widget_paintable_new(widget);
    gdk_paintable_snapshot(paintable, snapshot, width, height);
    g_object_unref(paintable);
  }
  gtk_snapshot_render_frame(snapshot, gtk_widget_get_style_context(background), 0, 0, width, height);
  GskRenderNode *node = gtk_snapshot_free_to_node(snapshot);
  if (!node) return 2;
  GskRenderer *renderer = gsk_cairo_renderer_new();
  if (!gsk_renderer_realize(renderer, NULL, NULL)) { gsk_render_node_unref(node); g_object_unref(renderer); return 4; }
  graphene_rect_t bounds = GRAPHENE_RECT_INIT(0, 0, width, height);
  GdkTexture *texture = gsk_renderer_render_texture(renderer, node, &bounds);
  int result = gdk_texture_save_to_png(texture, path) ? 0 : 3;
  g_object_unref(texture); gsk_render_node_unref(node);
  gsk_renderer_unrealize(renderer); g_object_unref(renderer);
  return result;
}
