#!/usr/bin/env python3
"""
Generate origami plot SVGs for engineer assessments.

Based on: Canadas-Gomez et al. (2023) "Origami plot: a novel multivariate
data visualization tool that improves radar chart"

Usage:
    python3 scripts/origami_plot.py --name "Jane Doe" --scores 2,3,4,4,4,2
    python3 scripts/origami_plot.py --name "Jane Doe" --scores 2,3,4,4,4,3 --calibrated 2,3,4,4,4,2 -o out.svg
"""

import argparse
import math
from pathlib import Path

DOMAINS = ["Craft", "Infra", "Domain", "Decomposition", "Systems", "PeerDev"]
MAX_SCORE = 4
AUX_RATIO = 0.15

COLOR_PRIMARY = "#2563eb"
COLOR_PRIMARY_FILL = "#2563eb20"
COLOR_CALIBRATED = "#dc2626"
COLOR_CALIBRATED_FILL = "#dc262620"
COLOR_GRID = "#d1d5db"
COLOR_AXIS = "#9ca3af"
COLOR_TEXT = "#374151"
COLOR_AUX_AXIS = "#d1d5db"


def polar_to_cart(angle_deg, radius, cx=300, cy=300):
    angle_rad = math.radians(90 - angle_deg)
    x = cx + radius * math.cos(angle_rad)
    y = cy - radius * math.sin(angle_rad)
    return x, y


def make_origami_points(scores, n_domains, max_radius=220):
    points = []
    angle_step = 360 / n_domains
    for i in range(n_domains):
        main_angle = i * angle_step
        main_r = (scores[i] / MAX_SCORE) * max_radius
        points.append(polar_to_cart(main_angle, main_r))
        aux_angle = main_angle + angle_step / 2
        aux_r = AUX_RATIO * max_radius
        points.append(polar_to_cart(aux_angle, aux_r))
    return points


def svg_polygon(points, stroke, fill, stroke_width=2, opacity=1):
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}" opacity="{opacity}" />'


def generate_svg(name, scores, calibrated=None, width=600, height=650):
    cx, cy = 300, 300
    max_radius = 220
    n = len(DOMAINS)
    angle_step = 360 / n

    lines = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" font-family="system-ui, -apple-system, sans-serif">')
    lines.append(f'<rect width="{width}" height="{height}" fill="white" />')
    lines.append(f'<text x="{cx}" y="30" text-anchor="middle" font-size="18" font-weight="600" fill="{COLOR_TEXT}">{name}</text>')

    for level in range(1, MAX_SCORE + 1):
        r = (level / MAX_SCORE) * max_radius
        lines.append(f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" stroke="#b0b7c3" stroke-width="0.5" stroke-dasharray="4,4" />')
        lx, ly = cx - 8, cy - r + 4
        lines.append(f'<text x="{lx}" y="{ly}" text-anchor="end" font-size="10" fill="{COLOR_AXIS}">{level}</text>')

    for i in range(n):
        main_angle = i * angle_step
        ex, ey = polar_to_cart(main_angle, max_radius + 10)
        lines.append(f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{COLOR_AXIS}" stroke-width="1" />')

        aux_angle = main_angle + angle_step / 2
        aex, aey = polar_to_cart(aux_angle, max_radius * 0.3)
        lines.append(f'<line x1="{cx}" y1="{cy}" x2="{aex:.1f}" y2="{aey:.1f}" stroke="{COLOR_AUX_AXIS}" stroke-width="0.5" stroke-dasharray="3,3" />')

        label_r = max_radius + 30
        lx, ly = polar_to_cart(main_angle, label_r)
        anchor = "middle"
        if main_angle > 10 and main_angle < 170:
            anchor = "start"
        elif main_angle > 190 and main_angle < 350:
            anchor = "end"
        dy = 5
        if main_angle < 10 or main_angle > 350:
            dy = -5
        elif abs(main_angle - 180) < 10:
            dy = 15
        lines.append(f'<text x="{lx:.1f}" y="{ly + dy:.1f}" text-anchor="{anchor}" font-size="13" font-weight="500" fill="{COLOR_TEXT}">{DOMAINS[i]}</text>')

    if calibrated:
        pts_orig = make_origami_points(scores, n, max_radius)
        lines.append(svg_polygon(pts_orig, COLOR_PRIMARY, COLOR_PRIMARY_FILL, stroke_width=1.5, opacity=0.5))
        pts_cal = make_origami_points(calibrated, n, max_radius)
        lines.append(svg_polygon(pts_cal, COLOR_CALIBRATED, COLOR_CALIBRATED_FILL, stroke_width=2))
        for i in range(n):
            main_angle = i * angle_step
            r = (calibrated[i] / MAX_SCORE) * max_radius
            px, py = polar_to_cart(main_angle, r)
            lines.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{COLOR_CALIBRATED}" />')
        for i in range(n):
            main_angle = i * angle_step
            r = (scores[i] / MAX_SCORE) * max_radius
            px, py = polar_to_cart(main_angle, r)
            lines.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="{COLOR_PRIMARY}" opacity="0.5" />')
        ly = height - 40
        lines.append(f'<line x1="160" y1="{ly}" x2="185" y2="{ly}" stroke="{COLOR_PRIMARY}" stroke-width="2" opacity="0.5" />')
        lines.append(f'<text x="190" y="{ly + 4}" font-size="12" fill="{COLOR_TEXT}">Data-Driven</text>')
        lines.append(f'<line x1="310" y1="{ly}" x2="335" y2="{ly}" stroke="{COLOR_CALIBRATED}" stroke-width="2" />')
        lines.append(f'<text x="340" y="{ly + 4}" font-size="12" fill="{COLOR_TEXT}">Calibrated</text>')
    else:
        pts = make_origami_points(scores, n, max_radius)
        lines.append(svg_polygon(pts, COLOR_PRIMARY, COLOR_PRIMARY_FILL, stroke_width=2))
        for i in range(n):
            main_angle = i * angle_step
            r = (scores[i] / MAX_SCORE) * max_radius
            px, py = polar_to_cart(main_angle, r)
            lines.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{COLOR_PRIMARY}" />')
        for i in range(n):
            aux_angle = i * angle_step + angle_step / 2
            aux_r = AUX_RATIO * max_radius
            px, py = polar_to_cart(aux_angle, aux_r)
            lines.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2" fill="{COLOR_AXIS}" opacity="0.4" />')

    label_scores = calibrated if calibrated else scores
    label_color = COLOR_CALIBRATED if calibrated else COLOR_PRIMARY
    for i in range(n):
        main_angle = i * angle_step
        r = (label_scores[i] / MAX_SCORE) * max_radius + 15
        lx, ly = polar_to_cart(main_angle, r)
        lines.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" font-size="14" font-weight="700" fill="{label_color}">{label_scores[i]}</text>')

    lines.append(f'<text x="{cx}" y="{height - 10}" text-anchor="middle" font-size="10" fill="{COLOR_AXIS}">1=Following  2=Owning  3=Driving  4=Shaping</text>')
    lines.append('</svg>')
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate origami plot SVG")
    parser.add_argument("--name", required=True, help="Engineer name")
    parser.add_argument("--scores", required=True, help="Comma-separated scores (6 values, 1-4)")
    parser.add_argument("--calibrated", help="Comma-separated calibrated scores (optional overlay)")
    parser.add_argument("--output", "-o", help="Output SVG path (default: stdout)")
    args = parser.parse_args()

    scores = [int(x.strip()) for x in args.scores.split(",")]
    if len(scores) != 6:
        print(f"Error: expected 6 scores, got {len(scores)}")
        return 1

    calibrated = None
    if args.calibrated:
        calibrated = [int(x.strip()) for x in args.calibrated.split(",")]
        if len(calibrated) != 6:
            print(f"Error: expected 6 calibrated scores, got {len(calibrated)}")
            return 1

    svg = generate_svg(args.name, scores, calibrated)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(svg)
        print(f"Written: {args.output}")
    else:
        print(svg)


if __name__ == "__main__":
    main()
