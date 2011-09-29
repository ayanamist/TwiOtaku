from time import time, sleep

from lib.thread import StoppableThread, threadstop


class MessageSender(StoppableThread):
  _count = 0
  _sum = 0
  _last_sent_time = 0
  num_per_second = 5
  continuous_sum = 10

  def __init__(self, queue):
    super(MessageSender, self).__init__()
    self._queue = queue

  @threadstop
  def run(self):
    while True:
      message = self._queue.get()
      if message is None:
        return
      self._count += 1
      remain_time = 1 - (time() - self._last_sent_time)
      if self._count >= self.num_per_second:
        if remain_time > 0:
          self._sum += 1
          if self._sum >= self.continuous_sum:
            # it seems we can't send messages continuously but have to rest for a while
            # http://stackoverflow.com/questions/1843837/what-is-the-throttling-rate-that-gtalk-applies-to-xmpp-messages
            sleep(2)
            self._sum = 0
          else:
            sleep(remain_time)
        else:
          self._sum = 0
        self._count = 0
      message.send()
      self._last_sent_time = time()
