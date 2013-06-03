# -*- encoding: utf-8 -*-

import sublime
import sublime_plugin
import os
import os.path
import functools
import threading
import subprocess
import urllib2
import simplejson as json


def main_thread(callback, *args, **kwargs):
    # sublime.set_timeout gets used to send things onto the main thread
    # most sublime.[something] calls need to be on the main thread
    sublime.set_timeout(functools.partial(callback, *args, **kwargs), 0)


class CommandThread(threading.Thread):
    def __init__(self, command, on_done, **kwargs):
        threading.Thread.__init__(self)
        self.on_done = on_done
        self.kwargs = kwargs

        if isinstance(command, list):
            self.command = str.join(' ', command)
        else:
            self.command = command

        if "stdin" in kwargs:
            self.stdin = kwargs["stdin"]
        else:
            self.stdin = None

        if "stdout" in kwargs:
            self.stdout = kwargs["stdout"]
        else:
            self.stdout = subprocess.PIPE

    def run(self):
        try:
            proc = subprocess.Popen(self.command,
                                    stdout=self.stdout,
                                    stderr=subprocess.STDOUT,
                                    stdin=subprocess.PIPE,
                                    shell=True,
                                    universal_newlines=True)
            # if sublime's python gets bumped to 2.7 we can just do:
            # output = subprocess.check_output(self.command)
            output = proc.communicate(self.stdin)[0] or ''
            main_thread(self.on_done, output, **self.kwargs)
        except Exception, e:
            main_thread(sublime.error_message, str(e))


class RemoteEditingCommand():
    def run_command(self, command, callback=None):
        callback = callback or self.generic_done
        thread = CommandThread(command, callback)
        thread.start()

    def generic_done(self, result):
        pass

    def lookup(self, query):
        args = query,
        t = threading.Thread(target=self.query_youdao, args=args)
        t.start()

    def query_youdao(self, query):
        settings = sublime.load_settings(__name__ + '.sublime-settings')
        query_url = 'http://fanyi.youdao.com/openapi.do?keyfrom=%s&key=%s&type=data&doctype=json&version=1.1&q=' + query
        query_url = query_url % (settings.get('keyfrom'), settings.get('key'))
        res = urllib2.urlopen(urllib2.Request(query_url))
        self.translation = json.loads(res.read())

        sublime.set_timeout(self.output, 0)

    def output(self):
        window = self.view.window()
        output_view = window.get_output_panel(__name__)
        window.run_command('show_panel', {'panel': 'output.%s' % __name__})
        output_view.set_read_only(False)
        edit = output_view.begin_edit()
        output = ''' %s [%s]
%s
'''
        explains = ''
        for explain in self.translation['basic']['explains']:
            explains += ' ' + explain + '\n'

        output = output % (self.translation['query'], self.translation['basic']['phonetic'], explains)
        output_view.insert(edit, output_view.size(), output)
        output_view.end_edit(edit)
        output_view.show(output_view.size())
        output_view.set_read_only(True)


class LookupForSelectionCommand(RemoteEditingCommand, sublime_plugin.TextCommand):
    def run(self, edit):
        for region in self.view.sel():
            if not region.empty():
                query = self.view.substr(region)
                self.lookup(query)
