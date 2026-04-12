from build123d import *
from viewer.render import render

cube = Box(30, 30, 30)
hole = Cylinder(8, 40)
result = cube - hole
result.color = Color("steelblue")

render("cube_with_hole", result)
