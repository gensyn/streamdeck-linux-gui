import os
from fractions import Fraction
from typing import Callable, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from streamdeck_ui.config import FONTS_PATH
from streamdeck_ui.display.filter import Filter


class TextFilter(Filter):
    # Static instance - no need to create one per Filter instance
    font_blur = None

    def __init__(self, text: str, font: str):
        super(TextFilter, self).__init__()
        self.text = text
        self.true_font = ImageFont.truetype(os.path.join(FONTS_PATH, font), 14)
        # fmt: off
        kernel = [
            0, 1, 2, 1, 0,
            1, 2, 4, 2, 1,
            2, 4, 8, 4, 1,
            1, 2, 4, 2, 1,
            0, 1, 2, 1, 0]
        # fmt: on
        TextFilter.font_blur = ImageFilter.Kernel((5, 5), kernel, scale=0.1 * sum(kernel))
        self.offset = 0.0
        self.offset_direction = 1
        self.image = None

        # Hashcode should be created for anything that makes this frame unique
        self.hashcode = hash((self.__class__, text, font))

    def initialize(self, size: Tuple[int, int]):
        self.image = Image.new("RGBA", size)
        backdrop_draw = ImageDraw.Draw(self.image)

        # TODO: The hard coded position should be improved
        # Note that you cannot simply take the height of the font
        # because it varies (for example, a "g" character) and
        # causes label alignment issues.
        label_w, label_h = backdrop_draw.textsize(self.text, font=self.true_font)
        label_pos = ((size[0] - label_w) // 2, size[1] - 20)

        backdrop_draw.text(label_pos, text=self.text, font=self.true_font, fill="black")
        self.image = self.image.filter(TextFilter.font_blur)

        foreground_draw = ImageDraw.Draw(self.image)
        foreground_draw.text(label_pos, text=self.text, font=self.true_font, fill="white")

    def transform(self, get_input: Callable[[], Image.Image], get_output: Callable[[int], Image.Image], input_changed: bool, time: Fraction) -> Tuple[Image.Image, int]:
        """
        The transformation returns the loaded image, ando overwrites whatever came before.
        """

        if input_changed:
            image = get_output(self.hashcode)
            if image:
                return (image, self.hashcode)

            input = get_input()
            input.paste(self.image, self.image)
            return (input, self.hashcode)
        return (None, self.hashcode)
