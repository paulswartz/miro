# Miro - an RSS based video player application
# Copyright (C) 2005, 2006, 2007, 2008, 2009, 2010, 2011
# Participatory Culture Foundation
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA
#
# In addition, as a special exception, the copyright holders give
# permission to link the code of portions of this program with the OpenSSL
# library.
#
# You must obey the GNU General Public License in all respects for all of
# the code used other than OpenSSL. If you modify file(s) with this
# exception, you may extend this exception to your version of the file(s),
# but you are not obligated to do so. If you do not wish to do so, delete
# this exception statement from your version. If you delete this exception
# statement from all source files in the program, then also delete it here.

"""browser.py -- portable browser code.  It checks if incoming URLs to see
what to do with them.
"""

import logging
from urlparse import urlparse

from miro import app
from miro import flashscraper
from miro import filetypes
from miro import messages
from miro import subscription
from miro import util
from miro.plat import resources
from miro.plat.frontends.widgets import timer
from miro.plat.frontends.widgets import widgetset
from miro.plat.frontends.widgets.threads import call_on_ui_thread
from miro.frontends.widgets import itemlistwidgets
from miro.frontends.widgets import separator
from miro.frontends.widgets import imagebutton
from miro.frontends.widgets import imagepool
from miro.frontends.widgets import widgetutil
from miro.gtcache import gettext as _

class BrowserLoadingImage(widgetset.HBox):

    THROBBER_WIDTH = 55
    DOWNLOAD_WIDTH = 62

    def __init__(self):
        widgetset.HBox.__init__(self)
        self.download = imagepool.get_image_display(
            resources.path('images/download-started.png'))
        self.throbber_shown = False
        self.download_shown = False
        self._width = None
        self.set_size_request(62, 37)

    @staticmethod
    def get_throbber():
        # XXX this is a hack; having one throbber attribute doesn't seem to
        # correctly re-pack it a second time
        return widgetset.AnimatedImageDisplay(
            resources.path('images/throbber.gif'))

    def do_size_allocated(self, width, height):
        if self._width != width:
            self._width = width
            self.redraw()

    def clear(self):
        for widget in list(self.children):
            self.remove(widget)

    def redraw(self):
        if self._width is None:
            # Haven't seen a size-allocated signal yet.  Wait until we get one
            # to draw ourselves
            return
        self.clear()
        available = self._width
        right_padding = 0
        if self.download_shown:
            self.pack_start(self.download)
            available -= self.DOWNLOAD_WIDTH
            right_padding = self.DOWNLOAD_WIDTH
        if (self.throbber_shown and
            available >= (self.THROBBER_WIDTH + right_padding)):
            self.pack_start(widgetutil.align_center(self.get_throbber(),
                                                    right_pad=right_padding),
                            expand=True)

    def set_throbber(self, value):
        if value != self.throbber_shown:
            self.throbber_shown = value
            self.redraw()

    def set_download(self, value):
        if value != self.download_shown:
            self.download_shown = value
            self.redraw()

class BrowserToolbar(itemlistwidgets.Titlebar):
    """
    Forward/back/home & "display in browser" buttons
    """
    def __init__(self):
        itemlistwidgets.Titlebar.__init__(self)

        hbox = widgetset.HBox()
        self.add(hbox)

        self.create_signal('browser-reload')
        self.create_signal('browser-back')
        self.create_signal('browser-forward')
        self.create_signal('browser-stop')
        self.create_signal('browser-home')
        self.create_signal('address-entered')
        self.create_signal('browser-download')
        self.create_signal('browser-open')

        self.back_button = imagebutton.ImageButton('navback')
        self.back_button.set_squish_width(True)
        self.back_button.connect('clicked', self._on_back_button_clicked)
        self.back_button.disable()
        hbox.pack_start(widgetutil.align_middle(self.back_button, left_pad=10))

        nav_separator = widgetset.ImageDisplay(imagepool.get(
            resources.path('images/navseparator.png')))
        hbox.pack_start(widgetutil.align_middle(nav_separator))

        self.forward_button = imagebutton.ImageButton('navforward')
        self.forward_button.set_squish_width(True)
        self.forward_button.connect('clicked', self._on_forward_button_clicked)
        self.forward_button.disable()
        hbox.pack_start(widgetutil.align_middle(self.forward_button))

        self.reload_button = imagebutton.ImageButton('navreload')
        self.reload_button.connect('clicked', self._on_reload_button_clicked)
        hbox.pack_start(widgetutil.align_middle(self.reload_button,
                                                left_pad=4))

        self.stop_button = imagebutton.ImageButton('navstop')
        self.stop_button.connect('clicked', self._on_stop_button_clicked)
        hbox.pack_start(widgetutil.align_middle(self.stop_button, left_pad=4))

        self.home_button = imagebutton.ImageButton('navhome')
        self.home_button.connect('clicked', self._on_home_button_clicked)
        hbox.pack_start(widgetutil.align_middle(self.home_button, left_pad=4))

        self.browser_open_button = widgetutil.TitlebarButton(
            _('Open in browser'), 'navopen')
        self.browser_open_button.connect(
            'clicked', self._on_browser_open_activate)
        hbox.pack_end(widgetutil.align_middle(self.browser_open_button,
                                              right_pad=10))

        self.download_button = widgetutil.TitlebarButton(
            _("Download this video"), 'navdownload')
        self.download_button.connect('clicked',
                                     self._on_download_button_clicked)
        self.download_button = widgetutil.HideableWidget(self.download_button)
        hbox.pack_end(widgetutil.align_middle(self.download_button,
                                              right_pad=4))

        self.loading_icon = BrowserLoadingImage()
        hbox.pack_start(widgetutil.align_middle(self.loading_icon),
                        expand=True)

    def _on_back_button_clicked(self, button):
        self.emit('browser-back')

    def _on_forward_button_clicked(self, button):
        self.emit('browser-forward')

    def _on_stop_button_clicked(self, button):
        self.emit('browser-stop')

    def _on_reload_button_clicked(self, button):
        self.emit('browser-reload')

    def _on_home_button_clicked(self, button):
        self.emit('browser-home')

    def _on_download_button_clicked(self, button):
        self.emit('browser-download')

    def _on_browser_open_activate(self, button):
        self.emit('browser-open')


class Browser(widgetset.Browser):
    def __init__(self, guide_info):
        widgetset.Browser.__init__(self)
        self.create_signal('download-started')
        self.guide_info = guide_info
        self.seen_cache = {}

    def handle_unknown_url(self, url):
        self.seen_cache[url] = 1
        self.navigate(url)

    def unknown_callback(self, url):
        """ callback to use for unknown URLs"""
        call_on_ui_thread(self.handle_unknown_url, url)

    def should_load_url(self, url):
        """Returns True if the Miro browser should handle the url and
        False otherwise.

        Situations which should return false:

        * if the url is something that Miro should download instead
        * other things?
        """
        logging.debug("got %s", url)

        if url in self.seen_cache:
            del self.seen_cache[url]
            return True

        url = util.to_uni(url)
        if subscription.is_subscribe_link(url):
            self.emit('download-started')
            messages.SubscriptionLinkClicked(url).send_to_backend()
            return False


        if filetypes.is_maybe_rss_url(url):
            logging.debug("miro wants to handle %s", url)
            self.emit('download-started')
            messages.DownloadURL(url, self.unknown_callback).send_to_backend()
            return False

        # parse the path out of the url and run that through the filetypes
        # code to see if it might be a video, audio or torrent file.
        # if so, try downloading it.
        ret = urlparse(url)
        if filetypes.is_allowed_filename(ret[2]):
            logging.debug("miro wants to handle %s", url)
            self.emit('download-started')
            messages.DownloadURL(url, self.unknown_callback).send_to_backend()
            return False

        if util.is_magnet_uri(url):
            logging.debug("miro wants to handle %s", url)
            self.emit('download-started')
            messages.DownloadURL(url, self.unknown_callback).send_to_backend()
            return False

        return True

    def should_load_mimetype(self, url, mimetype):
        """Like should_load_url(), but for mimetype checking.  """

        # FIXME: this never gets called on windows

        if filetypes.is_allowed_mimetype(mimetype):
            logging.debug("miro wants to handle %s", url)
            metadata = {'mime_type': mimetype}
            self.emit('download-started')
            messages.DownloadURL(url, self.unknown_callback,
                                 metadata).send_to_backend()
            return False

        return self.should_load_url(url)

    def should_download_url(self, url, mimetype):
        if filetypes.is_download_mimetype(mimetype):
            logging.debug('downloading %s (%s)', url, mimetype)
            return True
        return False

    def do_download_finished(self, url):
        logging.debug('finished downloading %s', url)
        self.emit('download-started')
        messages.DownloadURL(url, self.unknown_callback).send_to_backend()

class BrowserNav(widgetset.VBox):
    def __init__(self, guide_info):
        widgetset.VBox.__init__(self)
        self.browser = Browser(guide_info)
        self.toolbar = BrowserToolbar()
        self.guide_info = guide_info
        self.home_url = guide_info.url
        self.pack_start(self.toolbar)
        color1 = widgetutil.css_to_color('#bcbcbc')
        color2 = widgetutil.css_to_color('#020202')
        self.pack_start(separator.HSeparator(color1, color2))
        self.pack_start(self.browser, expand=True)

        self.toolbar.connect_weak('browser-back', self._on_browser_back)
        self.toolbar.connect_weak('browser-forward', self._on_browser_forward)
        self.toolbar.connect_weak('browser-reload', self._on_browser_reload)
        self.toolbar.connect_weak('browser-stop', self._on_browser_stop)
        self.toolbar.connect_weak('browser-home', self._on_browser_home)
        self.toolbar.connect_weak('browser-download',
                                  self._on_browser_download)
        self.toolbar.connect_weak('browser-open', self._on_browser_open)

        self.browser.connect_weak('net-start', self._on_net_start)
        self.browser.connect_weak('net-stop', self._on_net_stop)
        self.browser.connect_weak('download-started',
                                  self._on_download_started)

        self.browser.navigate(self.guide_info.url)

    def enable_disable_navigation(self):
        if self.browser.can_go_back():
            self.toolbar.back_button.enable()
        else:
            self.toolbar.back_button.disable()

        if self.browser.can_go_forward():
            self.toolbar.forward_button.enable()
        else:
            self.toolbar.forward_button.disable()

    def _on_net_start(self, widget):
        self.toolbar.stop_button.enable()
        self.enable_disable_navigation()
        self.toolbar.loading_icon.set_throbber(True)
        self.toolbar.download_button.hide()

    def _on_net_stop(self, widget):
        self.toolbar.stop_button.disable()
        self.enable_disable_navigation()
        self.toolbar.loading_icon.set_throbber(False)
        logging.debug("checking %s", self.browser.get_current_url())
        if flashscraper.is_maybe_flashscrapable(
            unicode(self.browser.get_current_url())):
            self.toolbar.download_button.show()

    def _on_browser_back(self, widget):
        self.browser.back()

    def _on_browser_forward(self, widget):
        self.browser.forward()

    def _on_browser_reload(self, widget):
        self.browser.reload()

    def _on_browser_stop(self, widget):
        self.browser.stop()

    def _on_browser_home(self, widget):
        self.browser.navigate(self.home_url)

    def _on_browser_download(self, widget):
        metadata = {"title": unicode(self.browser.get_current_title())}
        messages.DownloadURL(self.browser.get_current_url(),
                             metadata=metadata).send_to_backend()

    def _on_browser_open(self, widget):
        app.widgetapp.open_url(self.browser.get_current_url())

    def _on_download_started(self, widget):
        """
        Shows the download started icon for 5 seconds, then hide it.
        """
        self.toolbar.loading_icon.set_download(True)
        timer.add(5, lambda: self.toolbar.loading_icon.set_download(False))

    def destroy(self):
        self.browser.destroy()
