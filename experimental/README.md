# Experimental Components

This directory contains features, subsystems, and prototypes that are not currently considered part of Gabriel's core production runtime.

Code placed here may be under active development, subject to redesign, or temporarily isolated while architecture decisions are evaluated.

## Purpose

The goal of `experimental/` is to:

- Isolate non-essential functionality from the production code path
- Allow rapid iteration without affecting core services
- Provide a staging area for new capabilities
- Reduce complexity within daemon and executor modules
- Make future promotion or removal of experimental features easier