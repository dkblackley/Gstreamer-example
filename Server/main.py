#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import subprocess

import gi
import argparse

gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GstRtsp, GObject, GLib

# getting the required information from the user
parser = argparse.ArgumentParser()
parser.add_argument("--port", default=8554, help="port to stream video", type=int)
parser.add_argument("--stream_uri", required=True, help="endpoint you'd like to host on. i.e. <domain_name>/<endpoint>")
parser.add_argument("--debug", help="The desired level of debug, can be 0, 1 or 2", type=int, default=1)
opt = parser.parse_args()

Gst.init(None)
Gst.DebugLevel(5)
Gloop = GLib.MainLoop()
FILE_NAME = "sample-5s.mp4"


# Sensor Factory class which inherits the GstRtspServer base class and add
# properties to it.
class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, **properties):
        super(SensorFactory, self).__init__(**properties)

    def do_create_element(self, url):
        request_uri = url.get_request_uri()
        print('[INFO]: stream request on {}'.format(request_uri))
        launch_string = "filesrc location={} ! " \
                        "qtdemux name=demux demux.video_0 ! " \
                        "queue ! " \
                        "rtph264pay name=pay0 config-interval=1 pt=96".format(FILE_NAME)
        player = Gst.parse_launch(launch_string)

        # creates extended Gst.Bin with message debugging enabled
        self.extendedBin = ExtendedBin()
        self.extendedBin.add(player)

        # creates new Pipeline and adds extended Bin to it
        self.extendedPlayer = Gst.Pipeline.new("extendedPipeline")
        self.extendedPlayer.add(self.extendedBin)

        self.video_length = int(self.get_length(FILE_NAME))
        if int(opt.debug) >= 1:
            print("Video Length: " + str(self.video_length))
        # try:
        #     self.extendedBin.set_pid(self.pid)
        # except AttributeError:
        #     self.pid = GLib.timeout_add_seconds(self.video_length - 10, self.reset_pipeline)
        #     self.extendedBin.set_pid(self.pid)

        self.extendedPlayer.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            0
        )

        return self.extendedPlayer

    def get_length(self, filename):
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                 "format=duration", "-of",
                                 "default=noprint_wrappers=1:nokey=1", filename],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        return float(result.stdout)
    
    def reset_pipeline(self):
        if int(opt.debug) >=1:
            print("Video restarting")
            print("Killing PID: " + str(self.pid))
        self.extendedPlayer.seek_simple(
            Gst.Format.TIME,
            Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
            0
        )
        GLib.source_remove(self.pid)
        self.pid = GLib.timeout_add_seconds(self.video_length - 10, self.reset_pipeline)
        self.extendedBin.set_pid(self.pid)
    # attaching the source element to the rtsp media
    def do_configure(self, rtsp_media):
        # Make a new stream for the new joiner
        self.rtsp_media = rtsp_media
        rtsp_media.set_protocols(GstRtsp.RTSPLowerTrans.TCP)  # Only stream via TCP
        rtsp_media.set_reusable(False)
        rtsp_media.set_shared(True)
        print('[INFO]: Configure request on {}'.format(self.device_id))
        rtsp_media.set_stop_on_disconnect(True)
        rtsp_media.set_do_retransmission(False)
        print(rtsp_media.is_eos_shutdown())


# Rtsp server implementation where we attach the factory sensor with the stream uri
class GstServer(GstRtspServer.RTSPServer):
    def __init__(self, **properties):
        super(GstServer, self).__init__(**properties)
        self.factory = SensorFactory()
        print("GSTSERVER")
        self.set_service(str(opt.port))
        self.attach(None)

    def add_source(self, device_id):
        factory = SensorFactory()
        factory.device_id = device_id
        self.get_mount_points().add_factory("/" + device_id, factory)

# extended Gst.Bin that overrides do_handle_message and adds debugging
class ExtendedBin(Gst.Bin):
    def do_handle_message(self, message):
        if int(opt.debug) >= 2:
            if message.type == Gst.MessageType.ERROR:
                error, debug = message.parse_error()
                print("ERROR:", message.src.get_name(), ":", error.message)
                if debug:
                    print ("Debug info: " + debug)
            elif message.type == Gst.MessageType.EOS:
                print ("\n\nEnd of stream\n\n")
            elif message.type == Gst.MessageType.STATE_CHANGED:
                oldState, newState, pendingState = message.parse_state_changed()
                print ("State changed -> old:{}, new:{}, pending:{}".format(oldState, newState, pendingState))
            elif message.type == Gst.MessageType.STREAM_STATUS:
                incoming, owner = message.parse_stream_status()
                print ("message: {} Owner: {}".format(incoming, owner))
            else :
                print("Some other message type: " + str(message.type))
        if message.type == Gst.MessageType.STREAM_STATUS:
            incoming, owner = message.parse_stream_status()
            if incoming == Gst.StreamStatusType.LEAVE or incoming == Gst.StreamStatusType.DESTROY:
                if int(opt.debug) >= 2:
                    print("Killing PID: " + self.pid)
                GLib.source_remove(self.pid)
        #call base handler to enable message propagation
        Gst.Bin.do_handle_message(self, message)

    def set_pid(self, pid):
        if int(opt.debug) >= 1:
            print("Adding PID: " + str(pid))
        self.pid = pid



def start_RTSP():
    endpoints = opt.stream_uri.split(",")
    server = GstServer()

    for endpoint in endpoints:
        server.add_source(endpoint)
        print(f"--------------------------- STREAMING BEGUN AT /{endpoint} ------------------------------------")

    Gloop.run()

if __name__ == "__main__":
    start_RTSP()