import sys
import time
import m3u8

from Crypto.Cipher import AES

# from fHDHR.exceptions import TunerError


class Direct_M3U8_Stream():

    def __init__(self, fhdhr, stream_args, tuner):
        self.fhdhr = fhdhr
        self.stream_args = stream_args
        self.tuner = tuner

        self.bytes_per_read = int(self.fhdhr.config.dict["streaming"]["bytes_per_read"])

    def get(self):

        if not self.stream_args["duration"] == 0:
            self.stream_args["time_end"] = self.stream_args["duration"] + time.time()

        self.fhdhr.logger.info("Detected stream of m3u8 URL: %s" % self.stream_args["stream_info"]["url"])

        if self.stream_args["transcode_quality"]:
            self.fhdhr.logger.info("Client requested a %s transcode for stream. Direct Method cannot transcode." % self.stream_args["transcode_quality"])

        def generate():

            try:

                played_chunk_urls = []

                while self.tuner.tuner_lock.locked():

                    try:
                        if self.stream_args["stream_info"]["headers"]:
                            playlist = m3u8.load(self.stream_args["stream_info"]["url"], headers=self.stream_args["stream_info"]["headers"])
                        else:
                            playlist = m3u8.load(self.stream_args["stream_info"]["url"])
                    except Exception as e:
                        self.fhdhr.logger.info("Connection Closed: %s" % e)
                        self.tuner.close()
                        return None

                    segments = playlist.segments

                    if len(played_chunk_urls):
                        newsegments = 0
                        for segment in segments:
                            if segment.absolute_uri not in played_chunk_urls:
                                newsegments += 1
                        self.fhdhr.logger.info("Refreshing m3u8, Loaded %s new segments." % str(newsegments))
                    else:
                        self.fhdhr.logger.info("Loaded %s segments." % str(len(segments)))

                    if playlist.keys != [None]:
                        keys = [{"url": key.absolute_uri, "method": key.method, "iv": key.iv} for key in playlist.keys if key]
                    else:
                        keys = [None for i in range(0, len(segments))]

                    for segment, key in zip(segments, keys):
                        chunkurl = segment.absolute_uri

                        if chunkurl and chunkurl not in played_chunk_urls:
                            played_chunk_urls.append(chunkurl)

                            if (not self.stream_args["duration"] == 0 and
                               not time.time() < self.stream_args["time_end"]):
                                self.fhdhr.logger.info("Requested Duration Expired.")
                                self.tuner.close()

                            if self.stream_args["stream_info"]["headers"]:
                                chunk = self.fhdhr.web.session.get(chunkurl, headers=self.stream_args["stream_info"]["headers"]).content
                            else:
                                chunk = self.fhdhr.web.session.get(chunkurl).content
                            if not chunk:
                                break
                                # raise TunerError("807 - No Video Data")
                            if key:
                                if key["url"]:
                                    if self.stream_args["stream_info"]["headers"]:
                                        keyfile = self.fhdhr.web.session.get(key["url"], headers=self.stream_args["stream_info"]["headers"]).content
                                    else:
                                        keyfile = self.fhdhr.web.session.get(key["url"]).content
                                    cryptor = AES.new(keyfile, AES.MODE_CBC, keyfile)
                                    self.fhdhr.logger.info("Decrypting Chunk #%s with key: %s" % (len(played_chunk_urls), key["url"]))
                                    chunk = cryptor.decrypt(chunk)

                            chunk_size = int(sys.getsizeof(chunk))
                            self.fhdhr.logger.info("Passing Through Chunk #%s with size %s: %s" % (len(played_chunk_urls), chunk_size, chunkurl))
                            yield chunk
                            self.tuner.add_downloaded_size(chunk_size)

                self.fhdhr.logger.info("Connection Closed: Tuner Lock Removed")

            except GeneratorExit:
                self.fhdhr.logger.info("Connection Closed.")
            except Exception as e:
                self.fhdhr.logger.info("Connection Closed: %s" % e)
            finally:
                self.fhdhr.logger.info("Connection Closed: Tuner Lock Removed")
                if hasattr(self.fhdhr.origins.origins_dict[self.tuner.origin], "close_stream"):
                    self.fhdhr.origins.origins_dict[self.tuner.origin].close_stream(self.tuner.number, self.stream_args)
                self.tuner.close()
                # raise TunerError("806 - Tune Failed")

        return generate()
