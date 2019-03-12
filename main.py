from bokeh.plotting import figure
from bokeh.transform import linear_cmap
from bokeh.layouts import row, column, gridplot, layout
from bokeh.models import Circle, ColorBar, HoverTool
from bokeh.models.callbacks import CustomJS
from bokeh.models import ColumnDataSource, RadioButtonGroup, Slider, Div
from bokeh.io import curdoc
from bokeh.layouts import widgetbox
from bokeh.palettes import Spectral10 as palette
from bokeh.palettes import Category10
import itertools


from functools import partial
from threading import Thread

from tornado import gen

from helpers import TOOLS, TOOLTIP, DETAILS, ISOTHERMS, HOVER
from helpers import load_data, load_nist_isotherm, intersect


class Dashboard():

    def __init__(self):

        self.data_dict = load_data()

        # Parameters
        self.gases = ['carbon dioxide', 'nitrogen',
                      'methane', 'ethane', 'ethene']
        self.g0 = self.gases[0]
        self.g1 = self.gases[1]
        self.pressure = 0

        self.doc = curdoc()  # Save curdoc() for thread access

        # Bokeh specific data generation
        self.data = ColumnDataSource(data=self.gen_data())
        self.errors = ColumnDataSource(data=self.gen_error(None))
        self.s_g0iso = ColumnDataSource(data=self.gen_isos())
        self.s_g1iso = ColumnDataSource(data=self.gen_isos())

        # Data callback
        self.data.selected.on_change('indices', self.selection_callback)

        # Radio selections
        self.s_type = RadioButtonGroup(
            labels=["CO2 / N2", "CO2 / CH4", "C2H6 / C2H4"], active=0)
        self.s_type.on_click(self.s_type_callback)

        # Top graphs
        self.p_loading = None
        self.p_henry = None
        self.top_graphs()

        # Pressure slider
        self.slider = Slider(title="Pressure", value=0.5,
                             start=0.5, end=20, step=0.5)
        self.slider.on_change('value', self.pressure_callback)

        # Details text
        self.details = Div(text=self.gen_details(), width=500)
        self.details_iso = Div(text=self.gen_iso_text(), height=400)

        # Isotherms
        self.g0iso = []
        self.g1iso = []
        self.p_g0iso = None
        self.p_g1iso = None
        self.bottom_graphs()

        self.dash_layout = layout([
            [widgetbox(self.s_type)],
            [gridplot([[self.p_henry, self.p_loading]])],
            [widgetbox(children=[self.slider])],
            [self.details],
            [gridplot([[self.p_g0iso, self.p_g1iso]])],
            [self.details_iso],
        ], sizing_mode='scale_width')
        self.doc.title = "Graphs"

    def show_dash(self):
        self.doc.add_root(self.dash_layout)

    def top_graphs(self):

        mapper0 = self.mapper(0)
        mapper1 = self.mapper(1)

        plot_side_size = 500

        # create a new plot and add a renderer
        self.p_loading = figure(tools=TOOLS,
                                active_scroll="wheel_zoom",
                                plot_width=plot_side_size, plot_height=plot_side_size,
                                title='Uptake at selected pressure')

        # create another new plot and add a renderer
        self.p_henry = figure(tools=TOOLS,
                              active_scroll="wheel_zoom",
                              x_range=(1e-2, 1e5), y_range=(1e-2, 1e5),
                              plot_width=plot_side_size, plot_height=plot_side_size,
                              y_axis_type="log", x_axis_type="log",
                              title='Initial Henry constant')

        self.p_loading.add_tools(
            HoverTool(names=["datal", "datar"],
                      tooltips=TOOLTIP.render(p=0, gas0=self.g0, gas1=self.g1))
        )
        self.p_henry.add_tools(
            HoverTool(names=["datal", "datar"],
                      tooltips=TOOLTIP.render(p=1, gas0=self.g0, gas1=self.g1))
        )

        # Data
        rendl = self.p_loading.circle('x0', 'y0', source=self.data, size=10,
                                      line_color=mapper0, color=mapper0, name="datal")
        rendr = self.p_henry.circle('x1', 'y1', source=self.data, size=10,
                                    line_color=mapper1, color=mapper1, name="datar")

        # Errors
        errsl = self.p_loading.segment('x00', 'y00', 'x01', 'y01', source=self.errors,
                                       color="black", line_width=2)
        errsr = self.p_henry.segment('x10', 'y10', 'x11', 'y11', source=self.errors,
                                     color="black", line_width=2)

        # Colorbars
        color_bar0 = ColorBar(
            color_mapper=mapper0['transform'], width=8,  location=(0, 0))
        color_bar1 = ColorBar(
            color_mapper=mapper1['transform'], width=8,  location=(0, 0))
        self.p_loading.add_layout(color_bar0, 'right')
        self.p_henry.add_layout(color_bar1, 'right')

        # Add a linked selection and hover effect
        sel = Circle(fill_alpha=1, fill_color="black", line_color='red')
        rendl.selection_glyph = sel
        rendr.selection_glyph = sel
        rendl.hover_glyph = sel
        rendr.hover_glyph = sel

        # Generate labels:
        self.top_graph_label()

    def top_graph_label(self):
        self.p_loading.xaxis.axis_label = '{0} (mmol/g)'.format(self.g0)
        self.p_loading.yaxis.axis_label = '{0} (mmol/g)'.format(self.g1)
        self.p_henry.xaxis.axis_label = '{0} (dimensionless)'.format(
            self.g0)
        self.p_henry.yaxis.axis_label = '{0} (dimensionless)'.format(
            self.g1)

    def mapper(self, z):
        return linear_cmap(
            field_name='z{0}'.format(z), palette=palette,
            low_color='grey', high_color='red',
            low=3, high=90)

    def bottom_graphs(self):

        self.g0iso = []
        self.g1iso = []
        callback0 = CustomJS(
            args=dict(source=self.s_g0iso), code=HOVER.render())
        callback1 = CustomJS(
            args=dict(source=self.s_g1iso), code=HOVER.render())

        plot_side = 350

        self.p_g0iso = figure(tools=TOOLS, active_scroll="wheel_zoom",
                              plot_width=500, plot_height=plot_side,
                              title='Isotherms {0}'.format(self.g0))
        self.p_g0iso.multi_line('x', 'y', source=self.s_g0iso, alpha=0.6, line_width=2,
                                hover_line_alpha=1.0)
        self.p_g0iso.add_tools(HoverTool(show_arrow=False,
                                         line_policy='nearest',
                                         tooltips='@labels',
                                         callback=callback0))
        self.p_g0iso.xaxis.axis_label = 'Pressure (bar)'
        self.p_g0iso.yaxis.axis_label = 'Uptake (mmol/g)'

        self.p_g1iso = figure(tools=TOOLS, active_scroll="wheel_zoom",
                              plot_width=500, plot_height=plot_side,
                              title='Isotherms {0}'.format(self.g1))
        self.p_g1iso.multi_line('x', 'y', source=self.s_g1iso, alpha=0.6, line_width=2,
                                hover_line_alpha=1.0)
        self.p_g1iso.add_tools(HoverTool(show_arrow=False,
                                         line_policy='nearest',
                                         tooltips='@labels',
                                         callback=callback1))
        self.p_g1iso.xaxis.axis_label = 'Pressure (bar)'
        self.p_g1iso.yaxis.axis_label = 'Uptake (mmol/g)'

        self.iso_color = itertools.cycle(Category10[10])

    # #########################################################################
    # Data generator

    def gen_data(self):

        common = [mat for mat in self.data_dict if
                  self.data_dict[mat].get(self.g0, False) and
                  self.data_dict[mat].get(self.g1, False)]

        dd = self.data_dict
        g0 = self.g0
        g1 = self.g1
        p = self.pressure

        z0x = [dd[mat][g0]['lL'][p] for mat in common]
        z0y = [dd[mat][g1]['lL'][p] for mat in common]
        z1x = [dd[mat][g0]['lKh'] for mat in common]
        z1y = [dd[mat][g1]['lKh'] for mat in common]

        return dict(
            labels=common,
            x0=[dd[mat][g0]['mL'][p] for mat in common],
            y0=[dd[mat][g1]['mL'][p] for mat in common],
            x1=[dd[mat][g0]['mKh'] for mat in common],
            y1=[dd[mat][g1]['mKh'] for mat in common],
            z0x=z0x,
            z0y=z0y,
            z1x=z1x,
            z1y=z1y,
            z0=[z0x[a] + z0y[a] for a in range(len(z0x))],
            z1=[z1x[a] + z1y[a] for a in range(len(z1x))],
        )

    # #########################################################################
    # Error generator

    def gen_error(self, index):

        if index is None:
            return dict(
                x00=[], y00=[], x01=[], y01=[],
                x10=[], y10=[], x11=[], y11=[])

        else:
            p = self.pressure

            mat = self.data.data['labels'][index]
            x0 = self.data.data['x0'][index]
            y0 = self.data.data['y0'][index]
            xe00 = self.data_dict[mat][self.g0]['eL'][p]
            xe01 = self.data_dict[mat][self.g1]['eL'][p]
            x1 = self.data.data['x1'][index]
            y1 = self.data.data['y1'][index]
            xe10 = self.data_dict[mat][self.g0]['eKh']
            xe11 = self.data_dict[mat][self.g1]['eKh']

            e_dict = dict(
                labels=[mat, mat],
                x00=[x0 - xe00, x0],
                y00=[y0, y0-xe01],
                x01=[x0 + xe00, x0],
                y01=[y0, y0+xe01],
                x10=[x1 - xe10, x1],
                y10=[y1, y1-xe11],
                x11=[x1 + xe10, x1],
                y11=[y1, y1+xe11],
            )
            return e_dict

    # #########################################################################
    # Isotherms

    def gen_isos(self, lst=None):

        if lst is None:
            return dict(labels=[], x=[], y=[])

        else:
            labels = []
            xs = []
            ys = []

            for iso in lst:
                labels.append(iso.filename)
                xs.append(iso.pressure().tolist())
                ys.append(iso.loading().tolist())

            return dict(labels=labels, x=xs, y=ys)

    # #########################################################################
    # Text

    def gen_details(self, index=None):
        if index is None:
            return DETAILS.render()
        else:
            mat = self.data.data['labels'][index]
            p = self.pressure

            data = {
                'material': mat,
                'gas0': self.g0,
                'gas1': self.g1,
                'gas0_niso': len(self.data_dict[mat][self.g0]['iso']),
                'gas1_niso': len(self.data_dict[mat][self.g1]['iso']),
                'gas0_load': self.data.data['x0'][index],
                'gas1_load': self.data.data['y0'][index],
                'gas0_eload': self.data_dict[mat][self.g0]['eL'][p],
                'gas1_eload': self.data_dict[mat][self.g1]['eL'][p],
                'gas0_hk': self.data_dict[mat][self.g0]['mKh'],
                'gas1_hk': self.data_dict[mat][self.g1]['mKh'],
                'gas0_ehk': self.data_dict[mat][self.g0]['eKh'],
                'gas1_ehk': self.data_dict[mat][self.g1]['eKh'],
            }
            return DETAILS.render(**data)

    def gen_iso_text(self, lst=None):

        if lst is None:
            return ISOTHERMS.render()
        else:
            return ISOTHERMS.render(
                {'gas0_iso': self.g0iso, 'gas1_iso': self.g1iso})

    # #########################################################################
    # Isotherms

    def download_isos(self, index, which=None):

        if index is None:
            return

        else:
            mat = self.data.data['labels'][index]

            if which == 'right':
                isos = self.data_dict[mat][self.g0]['iso']
                source = self.s_g0iso
                lst = self.g0iso
            elif which == 'left':
                isos = self.data_dict[mat][self.g1]['iso']
                source = self.s_g1iso
                lst = self.g1iso
            else:
                raise Exception

            for iso in isos:
                parsed = load_nist_isotherm(iso)

                # update the document from callback
                if parsed:
                    lst.append(parsed)
                    self.doc.add_next_tick_callback(
                        partial(self.iso_update, source=source, lst=lst))

    # #########################################################################
    # Update
    @gen.coroutine
    def iso_update(self, source, lst, **kwargs):
        source.data = self.gen_isos(lst=lst)
        self.details_iso.text = self.gen_iso_text(lst=lst)

    # #########################################################################
    # Selection update

    def s_type_callback(self, index):

        # Reset any selected materials
        sel = self.data.selected.indices
        if sel:
            self.data.selected.update(indices=[])

        if index == 0:
            self.g0 = self.gases[0]
            self.g1 = self.gases[1]
            self.data.data = self.gen_data()
        elif index == 1:
            self.g0 = self.gases[0]
            self.g1 = self.gases[2]
            self.data.data = self.gen_data()
        elif index == 2:
            self.g0 = self.gases[4]
            self.g1 = self.gases[3]
            self.data.data = self.gen_data()
        else:
            raise Exception

        # Update labels
        self.top_graph_label()

        # Update bottom
        self.bottom_graphs()

    # #########################################################################
    # Set up pressure slider and callback

    def pressure_callback(self, attrname, old, new):
        self.pressure = int(self.slider.value * 2) - 1
        self.data.data = self.gen_data()
        sel = self.data.selected.indices
        if sel:
            self.details.text = self.gen_details(sel[0])
            self.details_iso.text = self.gen_iso_text(sel[0])
            self.errors.data = self.gen_error(sel[0])

    # #########################################################################
    # Callback for selection

    def selection_callback(self, attr, old, new):

        if len(new) == 1:
            # The user has selected a point

            # Display error points:
            self.errors.data = self.gen_error(new[0])

            # Generate material details
            self.details.text = self.gen_details(new[0])

            # Reset bottom graphs
            self.bottom_graphs()

            # Generate bottom graphs
            Thread(target=self.download_isos, args=[new[0], 'left']).start()
            Thread(target=self.download_isos, args=[new[0], 'right']).start()

        else:
            self.errors.data = self.gen_error(None)


dash = Dashboard()
dash.show_dash()