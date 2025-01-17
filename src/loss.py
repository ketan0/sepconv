# The VGG loss in this file is copied from
# https://github.com/ekgibbons/pytorch-sepconv/blob/master/python/_support/VggLoss.py
# The SsimLoss loss in this file is copied (with minor modifications) from
# https://github.com/Po-Hsun-Su/pytorch-ssim/blob/master/pytorch_ssim/__init__.py

from math import exp

import torch
import torch.nn.functional as F
import torchvision
import src.config as config
from torch import nn
from torch.autograd import Variable


class VggLoss(nn.Module):
    def __init__(self):
        super(VggLoss, self).__init__()

        model = torchvision.models.vgg19(pretrained=True).cuda()

        self.features = nn.Sequential(
            # stop at relu4_4 (-10)
            *list(model.features.children())[:-10]
        )

        for param in self.features.parameters():
            param.requires_grad = False

    def forward(self, output, target):
        outputFeatures = self.features(output)
        targetFeatures = self.features(target)

        loss = torch.norm(outputFeatures - targetFeatures, 2)

        return config.VGG_FACTOR * loss
    
class ColorPixelLoss(nn.Module):
    def __init__(self):
        super(ColorPixelLoss, self).__init__()
        self.rgb_colormap = (torch.Tensor([HTMLColorToPercentRGB(html_cs) for html_cs in [
            '#FFFFFF', '#E4E4E4', '#888888', '#222222', '#FFA7D1', '#E50000', '#E59500', '#A06A42',
            '#E5D900', '#94E044', '#02BE01', '#00E5F0', '#0083C7', '#0000EA', '#E04AFF', '#820080'
        ]])).cuda()
        print(self.rgb_colormap.shape)
        
    def forward(self, output, target):
        print(output.shape)
        print(torch.max(output))
        
        dist = output.view(output.shape[0], 3, -1, 1) - self.rgb_colormap.view(1, 3, 1, -1)
        print('dist: ', dist.shape)
        norm_dist = torch.norm(dist, dim=1)
        print('norm_dist: ', norm_dist.shape)
        min_dist = torch.min(norm_dist, 2)[0]
        print('min_dist: ', min_dist.shape)
        loss = torch.sum(min_dist)
        return config.COLOR_FACTOR * loss


class CombinedLoss(nn.Module):
    def __init__(self):
        super(CombinedLoss, self).__init__()
        self.vgg = VggLoss()
        self.l1 = nn.L1Loss()

    def forward(self, output, target) -> torch.Tensor:
        return self.vgg(output, target) + self.l1(output, target)

    
class CombinedLoss2(nn.Module):
    def __init__(self):
        super(CombinedLoss2, self).__init__()
        self.l1 = nn.L1Loss()
        self.color = ColorPixelLoss()

    def forward(self, output, target) -> torch.Tensor:
        a, b = self.l1(output, target), self.color(output, target)
        print('l1: {} color: {}'.format(a, b))
        return a + b

class SsimLoss(torch.nn.Module):
    def __init__(self, window_size=11, size_average=True):
        super(SsimLoss, self).__init__()
        self.window_size = window_size
        self.size_average = size_average
        self.channel = 1
        self.window = create_window(window_size, self.channel)

    def forward(self, img1, img2):
        (_, channel, _, _) = img1.size()

        if channel == self.channel and self.window.data.type() == img1.data.type():
            window = self.window
        else:
            window = create_window(self.window_size, channel)

            if img1.is_cuda:
                window = window.cuda(img1.get_device())
            window = window.type_as(img1)

            self.window = window
            self.channel = channel

        return -_ssim(img1, img2, window, self.window_size, channel, self.size_average)


def ssim(img1, img2, window_size=11, size_average=True):

    if len(img1.size()) == 3:
        img1 = torch.stack([img1], dim=0)
        img2 = torch.stack([img2], dim=0)

    (_, channel, _, _) = img1.size()
    window = create_window(window_size, channel)

    if img1.is_cuda:
        window = window.cuda(img1.get_device())
    window = window.type_as(img1)

    return _ssim(img1, img2, window, window_size, channel, size_average)


def gaussian(window_size, sigma):
    gauss = torch.Tensor([exp(-(x - window_size // 2) ** 2 / float(2 * sigma ** 2)) for x in range(window_size)])
    return gauss / gauss.sum()


def create_window(window_size, channel):
    _1D_window = gaussian(window_size, 1.5).unsqueeze(1)
    _2D_window = _1D_window.mm(_1D_window.t()).float().unsqueeze(0).unsqueeze(0)
    window = Variable(_2D_window.expand(channel, 1, window_size, window_size).contiguous())
    return window


def _ssim(img1, img2, window, window_size, channel, size_average=True):
    mu1 = F.conv2d(img1, window, padding=window_size // 2, groups=channel)
    mu2 = F.conv2d(img2, window, padding=window_size // 2, groups=channel)

    mu1_sq = mu1.pow(2)
    mu2_sq = mu2.pow(2)
    mu1_mu2 = mu1 * mu2

    sigma1_sq = F.conv2d(img1 * img1, window, padding=window_size // 2, groups=channel) - mu1_sq
    sigma2_sq = F.conv2d(img2 * img2, window, padding=window_size // 2, groups=channel) - mu2_sq
    sigma12 = F.conv2d(img1 * img2, window, padding=window_size // 2, groups=channel) - mu1_mu2

    C1 = 0.01 ** 2
    C2 = 0.03 ** 2

    ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))

    if size_average:
        return ssim_map.mean()
    else:
        return ssim_map.mean(1).mean(1).mean(1)

def HTMLColorToRGB(cs):
    """
    Converts #RRGGBB to an (R, G, B) tuple.
    """
    cs = cs.strip()
    if cs[0] == '#': cs = cs[1:]
    if len(cs) != 6:
        raise ValueError("input #%s is not in #RRGGBB format" % cs)
    r, g, b = cs[:2], cs[2:4], cs[4:]
    r, g, b = [int(n, 16) for n in (r, g, b)]
    return (r, g, b)

def HTMLColorToPercentRGB(cs):
    """
    Converts #RRGGBB to a (Red, Green, Blue) ratio-out-of-1 tuple, as used by matplotlib.
    """
    return [c / 256 for c in HTMLColorToRGB(cs)]