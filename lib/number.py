def digit_to_alpha(digit):
  if not isinstance(digit, int):
    raise TypeError('Only accept digit argument.')
  nums = list()
  digit += 1
  while digit > 26:
    t = digit % 26
    if t > 0:
      nums.insert(0, t)
      digit //= 26
    else:
      nums.insert(0, 26)
      digit = digit // 26 - 1
  nums.insert(0, digit)
  return ''.join([chr(x + 64) for x in nums])


def alpha_to_digit(alpha):
  if not (isinstance(alpha, str) and alpha.isalpha()):
    raise TypeError('Only accept alpha argument.')
  return reduce(lambda x, y: x * 26 + y, [ord(x) - 64 for x in alpha]) - 1
  